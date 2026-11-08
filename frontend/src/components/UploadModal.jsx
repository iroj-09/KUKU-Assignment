import React, { useState, useRef } from 'react';
import { unquote } from '../utils/text';
import { ArrowLeft, Upload, X, FileText, CheckCircle2, Sparkles, ArrowRight } from 'lucide-react';
import { parseFile, generateCandidatesFromScript } from '../utils/clientParser';
import { savedResultsFor } from '../utils/knownResults';
import { byScoreThenRank } from '../utils/ranking';
import { evaluateCandidateWithGemini, isModelConfigured } from '../utils/geminiEvaluator';

// One line per uploaded file: how many promos it gave, or why it gave none.
function FileReport({ report, minDur }) {
  const tone = {
    ok: 'bg-emerald-50/70 border-emerald-200 text-emerald-900',
    empty: 'bg-amber-50 border-amber-200 text-amber-900',
    error: 'bg-rose-50 border-rose-200 text-rose-900',
  };
  const label = (r) =>
    r.status === 'ok'
      ? `${r.count} promo${r.count === 1 ? '' : 's'}${r.saved ? ' · saved pipeline results' : ''}`
      : r.status === 'empty'
        ? `No promo windows (needs timestamped scenes of at least ${minDur}s)`
        : `Could not read: ${r.message}`;
  return (
    <ul className="space-y-1.5 text-xs" aria-label="File results">
      {report.map((r) => (
        <li key={r.name} className={`flex items-start justify-between gap-3 rounded-lg border px-3 py-2 ${tone[r.status]}`}>
          <span className="truncate font-medium">{r.name}</span>
          <span className="max-w-[60%] shrink-0 text-right">{label(r)}</span>
        </li>
      ))}
    </ul>
  );
}

// `asPage` renders the same uploader as a normal page (used by the Home page's second option)
// instead of a floating dialog.
export default function UploadModal({ isOpen, onClose, onPromosGenerated, asPage = false }) {
  const [files, setFiles] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [minDur, setMinDur] = useState(20);
  const [maxDur, setMaxDur] = useState(60);
  const [maxPerScript, setMaxPerScript] = useState(6);
  const [useGeminiAuto, setUseGeminiAuto] = useState(false);
  const [progressMsg, setProgressMsg] = useState('');
  const [generatedResults, setGeneratedResults] = useState(null);
  const [fileReport, setFileReport] = useState([]);
  const [processError, setProcessError] = useState('');
  const fileInputRef = useRef(null);

  if (!isOpen) return null;

  // Add newly chosen files to the current selection (skipping exact duplicates).
  const addFiles = (incoming) => {
    const list = Array.from(incoming || []);
    if (list.length === 0) return;
    setFiles((prev) => {
      const key = (f) => `${f.name}|${f.size}|${f.lastModified}`;
      const seen = new Set(prev.map(key));
      return [...prev, ...list.filter((f) => !seen.has(key(f)))];
    });
    setGeneratedResults(null);
  };

  const removeFile = (idx) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
    setGeneratedResults(null);
  };

  const clearFiles = () => {
    setFiles([]);
    setGeneratedResults(null);
  };

  const handleFileChange = (e) => {
    addFiles(e.target.files);
    // Reset so choosing the same file again after removing it still fires onChange.
    e.target.value = '';
  };

  const handleDrop = (e) => {
    e.preventDefault();
    addFiles(e.dataTransfer.files);
  };

  const handleProcess = async () => {
    if (files.length === 0) return;
    if (!(minDur >= 5) || !(maxDur > minDur)) {
      alert('Max duration must be greater than min duration (and min at least 5s).');
      return;
    }
    setProcessError('');
    setFileReport([]);
    setIsProcessing(true);
    const allGenerated = [];
    const report = [];

    // Step 1: Parse and generate beat-aligned candidate windows (Zero API cost)
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      setProgressMsg(`Parsing ${file.name} (${i + 1}/${files.length})...`);
      await new Promise((r) => setTimeout(r, 60));

      try {
        // A file this project already analysed shows the saved pipeline results (the submitted raw outputs).
        const saved = await savedResultsFor(file);
        let candidates;
        if (saved) {
          candidates = saved.map((c) => ({ ...c }));
        } else {
          const text = await file.text();
          const parsed = parseFile(text, file.name);
          candidates = generateCandidatesFromScript(parsed, minDur, maxDur, maxPerScript);
        }
        // Tag each clip with its source file so it can be removed per-file later.
        // Each clip's id includes its file name, so the same episode number in two files stays two clips.
        allGenerated.push(...candidates.map((c) => ({ ...c, id: `upload:${file.name}|${c.id}`, sourceFile: file.name })));
        report.push({ name: file.name, status: candidates.length ? 'ok' : 'empty', count: candidates.length, saved: Boolean(saved) });
      } catch (err) {
        console.error(`Error processing ${file.name}:`, err);
        report.push({ name: file.name, status: 'error', message: err.message || 'unknown error' });
      }
    }

    setFileReport(report);

    if (allGenerated.length === 0) {
      setIsProcessing(false);
      setProgressMsg('');
      setProcessError('No promo windows were found. Check that the files contain timestamped scenes (e.g. Start: (00:00.00) | End: (00:05.00), or .srt timecodes).');
      return;
    }

    // Rank by local score first so "top 3" really means the best three across all files.
    allGenerated.sort(byScoreThenRank);

    // Step 2: Optional Gemini Evaluation (Only if user toggled it ON)
    if (useGeminiAuto) {
      if (!isModelConfigured()) {
        alert('No AI model is connected, so these promos use local scoring. Click "AI Model" in the top bar to connect one.');
      } else {
        const topToEvaluate = allGenerated.filter((c) => c.geminiScore == null).slice(0, 3);
        let geminiFailures = 0;
        let geminiFatal = null;
        for (let j = 0; j < topToEvaluate.length; j++) {
          setProgressMsg(`AI Evaluating candidate ${j + 1} of ${topToEvaluate.length}...`);
          try {
            const updated = await evaluateCandidateWithGemini(topToEvaluate[j]);
            allGenerated[allGenerated.indexOf(topToEvaluate[j])] = updated;
          } catch (gemErr) {
            console.warn('Gemini eval warning:', gemErr);
            geminiFailures += 1;
            if ([400, 401, 403, 404, 429].includes(gemErr.status)) {
              geminiFatal = gemErr.message;
              break;
            }
          }
          if (j + 1 < topToEvaluate.length) {
            await new Promise((r) => setTimeout(r, 1000));
          }
        }
        if (geminiFatal) {
          alert(`AI evaluation stopped: ${geminiFatal}\nPromos were generated with local scoring.`);
        } else if (geminiFailures > 0) {
          alert(`${geminiFailures} AI evaluation(s) failed; those promos keep local scoring.`);
        }
      }
    }

    setIsProcessing(false);
    setProgressMsg('');

    // Sort by hybrid score
    allGenerated.sort(byScoreThenRank);
    setGeneratedResults(allGenerated);
  };

  const handleConfirm = () => {
    if (generatedResults) {
      onPromosGenerated(generatedResults, files.map((f) => f.name));
      // Start fresh next time instead of re-showing this result screen.
      setFiles([]);
      setGeneratedResults(null);
      if (!asPage) onClose();
    }
  };

  return (
    <div
      className={
        asPage
          ? 'py-2'
          : 'fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fadeIn'
      }
    >
      <div
        className={`relative w-full max-w-2xl bg-white border border-slate-200 rounded-3xl p-6 sm:p-8 space-y-6 ${
          asPage ? 'mx-auto shadow-sm' : 'shadow-2xl'
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-rose-50 border border-rose-200 flex items-center justify-center text-rose-600">
              <Upload className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                Upload & Generate Promo Clips
              </h2>
              <p className="text-xs text-slate-500">
                Upload screenplay (.txt), subtitle (.srt), or Fountain (.fountain) files
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          >
            {asPage ? (
              <span className="inline-flex items-center gap-1 px-1 text-xs font-semibold">
                <ArrowLeft className="w-4 h-4" /> Back
              </span>
            ) : (
              <X className="w-5 h-5" />
            )}
          </button>
        </div>

        {/* Upload Dropzone */}
        {!generatedResults && (
          <>
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-slate-200 hover:border-rose-400 bg-slate-50/70 hover:bg-slate-50 rounded-2xl p-8 text-center cursor-pointer transition-all"
            >
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".txt,.srt,.fountain"
                onChange={handleFileChange}
                className="hidden"
              />
              <FileText className="w-10 h-10 text-rose-500 mx-auto mb-3" />
              <div className="text-sm font-bold text-slate-800">
                Drag & drop files here, or <span className="text-rose-600 underline">browse</span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Supports Kuku Screenplay TXT, SubRip SRT subtitles, and Fountain screenplays
              </p>
            </div>

            {/* Selected Files List */}
            {files.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold text-slate-700">
                    Selected Files ({files.length}):
                  </div>
                  <button
                    type="button"
                    onClick={clearFiles}
                    className="text-[11px] font-semibold text-slate-500 hover:text-rose-600"
                  >
                    Clear all
                  </button>
                </div>
                <div className="max-h-32 overflow-y-auto space-y-1 bg-slate-50 p-2.5 rounded-xl border border-slate-200">
                  {files.map((file, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between text-xs text-slate-800 bg-white border border-slate-200 px-3 py-1.5 rounded-lg shadow-xs"
                    >
                      <span className="truncate max-w-sm font-medium">{file.name}</span>
                      <span className="flex items-center gap-2 shrink-0">
                        <span className="text-slate-500 text-[10px]">
                          {(file.size / 1024).toFixed(1)} KB
                        </span>
                        <button
                          type="button"
                          onClick={() => removeFile(idx)}
                          title={`Remove ${file.name}`}
                          aria-label={`Remove ${file.name}`}
                          className="p-0.5 rounded text-slate-400 hover:text-rose-600 hover:bg-rose-50"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(processError || fileReport.some((r) => r.status !== 'ok')) && (
              <div role="alert" className="space-y-2">
                {processError && (
                  <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-medium text-rose-800">{processError}</p>
                )}
                <FileReport report={fileReport} minDur={minDur} />
              </div>
            )}

            {/* Candidate Generation Settings */}
            <div className="grid grid-cols-3 gap-3 bg-slate-50 p-4 rounded-xl border border-slate-200 text-xs">
              <div>
                <label className="text-slate-500 text-[11px] font-semibold block mb-1">Min Duration</label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    min="10"
                    max="45"
                    value={minDur}
                    onChange={(e) => setMinDur(Number(e.target.value))}
                    className="w-full bg-white border border-slate-200 rounded px-2.5 py-1 text-slate-900 text-xs font-bold focus:border-rose-500 focus:outline-none"
                  />
                  <span className="text-slate-500">s</span>
                </div>
              </div>

              <div>
                <label className="text-slate-500 text-[11px] font-semibold block mb-1">Max Duration</label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    min="30"
                    max="120"
                    value={maxDur}
                    onChange={(e) => setMaxDur(Number(e.target.value))}
                    className="w-full bg-white border border-slate-200 rounded px-2.5 py-1 text-slate-900 text-xs font-bold focus:border-rose-500 focus:outline-none"
                  />
                  <span className="text-slate-500">s</span>
                </div>
              </div>

              <div>
                <label className="text-slate-500 text-[11px] font-semibold block mb-1">Clips Per Script</label>
                <input
                  type="number"
                  min="1"
                  max="20"
                  value={maxPerScript}
                  onChange={(e) => setMaxPerScript(Number(e.target.value))}
                  className="w-full bg-white border border-slate-200 rounded px-2.5 py-1 text-slate-900 text-xs font-bold focus:border-rose-500 focus:outline-none"
                />
              </div>
            </div>

            {/* Optional Gemini AI Auto-Evaluation Toggle */}
            <div className="flex items-center justify-between p-4 bg-slate-50 rounded-xl border border-slate-200 text-xs">
              <div className="flex items-center gap-2.5">
                <Sparkles className="w-4 h-4 text-amber-500 flex-shrink-0" />
                <div>
                  <span className="font-bold text-slate-900 block">Auto-Evaluate with AI</span>
                  <span className="text-[10px] text-slate-500">
                    {useGeminiAuto ? 'Asks your connected AI model about the top 3 candidates' : 'Off: Instant local scoring (Zero API cost)'}
                  </span>
                </div>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={useGeminiAuto}
                  onChange={(e) => setUseGeminiAuto(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-9 h-5 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-amber-500"></div>
              </label>
            </div>

            {/* Action Buttons */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-500 hover:text-slate-800"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={files.length === 0 || isProcessing}
                onClick={handleProcess}
                className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white text-xs font-bold shadow-md shadow-rose-600/20 transition-all"
              >
                {isProcessing ? (
                  <>
                    <Sparkles className="w-4 h-4 animate-spin" />
                    <span>{progressMsg || 'Processing...'}</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    <span>Generate Beat-Aligned Promos</span>
                  </>
                )}
              </button>
            </div>
          </>
        )}

        {/* Results Screen */}
        {generatedResults && (
          <div className="space-y-6 text-center py-4">
            <div className="w-16 h-16 bg-emerald-50 text-emerald-600 border border-emerald-200 rounded-2xl flex items-center justify-center mx-auto shadow-xs">
              <CheckCircle2 className="w-8 h-8" />
            </div>

            <div>
              <h3 className="text-xl font-bold text-slate-900">Promo Discovery Complete!</h3>
              <p className="text-xs text-slate-500 mt-1">
                Generated <strong className="text-emerald-700 font-bold">{generatedResults.length} high-tension candidate promos</strong> from {files.length} script file(s).
              </p>
            </div>

            {fileReport.length > 0 && (
              <div className="text-left">
                <div className="mb-1.5 text-xs font-semibold text-slate-700">File results</div>
                <FileReport report={fileReport} minDur={minDur} />
              </div>
            )}

            {/* Top candidate preview */}
            {generatedResults[0] && (
              <div className="p-4 bg-slate-50 rounded-2xl border border-slate-200 text-left text-xs space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-900">#1 Pick: {generatedResults[0].episode}</span>
                  <span className="text-emerald-700 font-bold">{generatedResults[0].clipStart}s–{generatedResults[0].clipEnd}s ({generatedResults[0].duration}s)</span>
                </div>
                <p className="text-slate-700 italic">"{unquote(generatedResults[0].hook)}"</p>
              </div>
            )}

            <div className="flex items-center justify-center gap-3 pt-2">
              <button
                onClick={() => setGeneratedResults(null)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-500 hover:text-slate-800"
              >
                Upload Different Files
              </button>
              <button
                onClick={handleConfirm}
                className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold shadow-md shadow-rose-600/20 transition-all hover:scale-[1.01]"
              >
                <span>Explore Generated Promos</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
