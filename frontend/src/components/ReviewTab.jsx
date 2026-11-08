import React, { useState, useRef, useEffect } from 'react';
import EmptyState from './EmptyState';
import { unquote } from '../utils/text';
import {
  CheckSquare, CheckCircle, XCircle, AlertCircle, Save, Download, Upload,
  ChevronLeft, ChevronRight, SkipForward, FileText, Film, Play,
} from 'lucide-react';
import { downloadFile } from '../utils/nleExport';

const STATUSES = ['Approved', 'Rejected', 'Needs Further Review'];

const VERDICTS = [
  { id: 'Approved', label: 'Approve for Edit', icon: CheckCircle, activeClass: 'bg-emerald-600 text-white border-emerald-600 shadow-sm', inactiveClass: 'bg-slate-50 hover:bg-emerald-50 text-slate-700 border-slate-200 hover:border-emerald-300' },
  { id: 'Rejected', label: 'Reject Candidate', icon: XCircle, activeClass: 'bg-rose-600 text-white border-rose-600 shadow-sm', inactiveClass: 'bg-slate-50 hover:bg-rose-50 text-slate-700 border-slate-200 hover:border-rose-300' },
  { id: 'Needs Further Review', label: 'Needs Re-trimming', icon: AlertCircle, activeClass: 'bg-amber-600 text-white border-amber-600 shadow-sm', inactiveClass: 'bg-slate-50 hover:bg-amber-50 text-slate-700 border-slate-200 hover:border-amber-300' },
];

const btnSecondary =
  'inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 text-xs font-semibold shadow-xs';

export default function ReviewTab({ candidates, reviews, setReviews, selectedCandidate, onOpenExplorer, onOpenSimulator }) {
  // Start on the clip the user came from (e.g. the Explorer's "Review" button), not always rank #1.
  const initialId = selectedCandidate?.id || candidates[0]?.id || '';
  const [selectedId, setSelectedId] = useState(initialId);
  const [notes, setNotes] = useState(() => reviews[initialId]?.notes || '');
  // Nothing is pre-selected: an unreviewed clip must not look (or get saved as) approved.
  const [decision, setDecision] = useState(() => reviews[initialId]?.status || '');
  const [savedNote, setSavedNote] = useState('');

  const importInputRef = useRef(null);
  const [importMsg, setImportMsg] = useState('');

  const current = candidates.find((c) => c.id === selectedId) || candidates[0];
  const currentReview = reviews[current?.id];

  // Counts describe the clips being viewed, not reviews saved for another drama.
  const viewReviews = candidates.map((c) => reviews[c.id]).filter(Boolean);
  const approvedCount = viewReviews.filter((r) => r.status === 'Approved').length;
  const rejectedCount = viewReviews.filter((r) => r.status === 'Rejected').length;
  const needsReviewCount = viewReviews.filter((r) => r.status === 'Needs Further Review').length;
  const allSavedCount = Object.keys(reviews).length;

  const dirty = currentReview
    ? currentReview.status !== decision || (currentReview.notes || '') !== notes
    : decision !== '' || notes.trim() !== '';

  const persistReviews = (next) => {
    setReviews(next);
    try {
      localStorage.setItem('kuku_human_reviews', JSON.stringify(next));
    } catch (e) {
      console.error('Could not persist reviews', e);
    }
  };

  const buildReview = (status, noteText) => ({
    status,
    notes: noteText,
    reviewedAt: new Date().toISOString(),
    candidateId: current.id,
    episode: current.episode,
    rank: current.rank,
    hybridScore: current.hybridScore,
  });

  const handleSaveReview = () => {
    if (!current || !decision) return;
    persistReviews({ ...reviews, [current.id]: buildReview(decision, notes) });
    setSavedNote(`Saved: ${decision}`);
  };

  // ---- moving between clips, and keyboard shortcuts for fast sign-off ----
  const idx = candidates.findIndex((c) => c.id === current?.id);

  const selectCandidateId = (id, map = reviews) => {
    setSelectedId(id);
    const existing = map[id];
    setDecision(existing?.status || '');
    setNotes(existing?.notes || '');
    setSavedNote('');
  };

  // Moving away from a clip with unsaved changes asks first, so notes are never lost silently.
  const moveTo = (id) => {
    if (!id || id === current?.id) return;
    if (dirty && !window.confirm('You have unsaved changes for this clip. Move on without saving?')) return;
    selectCandidateId(id);
  };

  const goRelative = (step) => {
    const n = candidates.length;
    if (n) moveTo(candidates[(idx + step + n) % n].id);
  };

  const findNextUnreviewed = (map) => {
    const n = candidates.length;
    for (let k = 1; k <= n; k += 1) {
      const c = candidates[(idx + k) % n];
      if (!map[c.id]) return c;
    }
    return null;
  };

  const goNextUnreviewed = () => {
    const next = findNextUnreviewed(reviews);
    if (next) moveTo(next.id);
    else setSavedNote('All clips are reviewed');
  };

  // A / R / N: save that verdict (with the current notes) and jump to the next clip still to review.
  const decide = (status) => {
    if (!current) return;
    const updated = { ...reviews, [current.id]: buildReview(status, notes) };
    persistReviews(updated);
    const next = findNextUnreviewed(updated);
    if (next) {
      selectCandidateId(next.id, updated);
      setSavedNote(`Saved: ${status} · moved to the next unreviewed clip`);
    } else {
      setDecision(status);
      setSavedNote(`Saved: ${status} · all clips are reviewed`);
    }
  };

  // Re-subscribed every render so the handlers always see the latest state.
  useEffect(() => {
    const onKey = (e) => {
      // One action per key press (holding a key must not sign off a whole run of clips), and
      // never while typing, composing text, or behind an open dialog.
      if (e.repeat || e.isComposing) return;
      if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;
      if (document.querySelector('[role="dialog"]')) return;
      const el = e.target;
      if (el && (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable)) return;
      const status = { a: 'Approved', r: 'Rejected', n: 'Needs Further Review' }[e.key.toLowerCase()];
      if (status) {
        e.preventDefault();
        decide(status);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        goRelative(1);
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        goRelative(-1);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const handleExportReviewsJson = () => {
    downloadFile(
      JSON.stringify({ version: 1, exportedAt: new Date().toISOString(), reviews }, null, 2),
      'kuku_human_reviews_backup.json',
      'application/json'
    );
  };

  const handleImportReviewsJson = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      const incoming = parsed?.reviews && typeof parsed.reviews === 'object' ? parsed.reviews : parsed;
      const entries = Object.entries(incoming || {});
      // Only real verdicts are accepted; anything else in the file is skipped, not guessed at.
      const valid = Object.fromEntries(entries.filter(([, r]) => r && typeof r === 'object' && STATUSES.includes(r.status)));
      const count = Object.keys(valid).length;
      if (count === 0) throw new Error('no valid reviews found in file');
      const skipped = entries.length - count;
      // Merge: the newer reviewedAt wins when both sides reviewed the same clip.
      const merged = { ...reviews };
      Object.entries(valid).forEach(([id, r]) => {
        const mine = merged[id];
        if (!mine || (r.reviewedAt || '') >= (mine.reviewedAt || '')) merged[id] = r;
      });
      persistReviews(merged);
      setImportMsg(`Imported ${count} review${count === 1 ? '' : 's'}.${skipped ? ` ${skipped} skipped (unknown verdict).` : ''}`);
    } catch (err) {
      setImportMsg(`Import failed: ${err.message}`);
    }
  };

  const handleExportReviewsCsv = () => {
    const rows = [['Candidate ID', 'Episode', 'Rank', 'Hybrid Score', 'Decision', 'Reviewer Notes', 'Reviewed At']];
    viewReviews.forEach((r) => {
      rows.push([r.candidateId, r.episode, r.rank, r.hybridScore, r.status, r.notes || '', r.reviewedAt]);
    });

    // Quote every field and neutralise spreadsheet formulas (=, +, -, @).
    const esc = (v) => {
      let s = v == null ? '' : String(v);
      if (/^[=+\-@\t\r]/.test(s) && Number.isNaN(Number(s))) s = `'${s}`;
      return `"${s.replace(/"/g, '""')}"`;
    };
    downloadFile(rows.map((r) => r.map(esc).join(',')).join('\n'), 'kuku_human_reviews.csv', 'text/csv');
  };

  if (!candidates.length) {
    return (
      <EmptyState icon={CheckSquare} title="Nothing to review">
        There are no promos in this view yet.
      </EmptyState>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Top Banner & Stats */}
      <div className="bg-white border border-slate-200/90 p-5 rounded-2xl shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <CheckSquare className="w-4 h-4 text-emerald-600" /> Human Editorial Sign-Off
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Validate AI candidate cuts before exporting to video editing timeline.{' '}
            <span className="font-medium text-slate-600">
              {viewReviews.length} of {candidates.length} reviewed
            </span>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="px-3 py-1 bg-emerald-50 border border-emerald-200 rounded-xl text-xs font-bold text-emerald-700">
            {approvedCount} Approved
          </div>
          <div className="px-3 py-1 bg-rose-50 border border-rose-200 rounded-xl text-xs font-bold text-rose-700">
            {rejectedCount} Rejected
          </div>
          <div className="px-3 py-1 bg-amber-50 border border-amber-200 rounded-xl text-xs font-bold text-amber-700">
            {needsReviewCount} Needs Review
          </div>
        </div>
      </div>

      {/* Review Form Card */}
      <div className="bg-white border border-slate-200/90 p-6 rounded-2xl space-y-6 shadow-xs">
        {/* Candidate Selector */}
        <div className="space-y-1.5">
          <label htmlFor="review-candidate" className="text-xs font-semibold text-slate-700">
            Select Candidate for Review:
          </label>
          <select
            id="review-candidate"
            value={selectedId}
            onChange={(e) => moveTo(e.target.value)}
            className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 font-medium focus:bg-white focus:outline-none focus:border-rose-500"
          >
            {candidates.map((c) => {
              const rev = reviews[c.id];
              return (
                <option key={c.id} value={c.id}>
                  Rank #{c.rank} · {c.episode} ({c.clipStart}–{c.clipEnd}s, Hybrid: {c.hybridScore}){rev ? ` [${rev.status}]` : ''}
                </option>
              );
            })}
          </select>
        </div>

        {/* Moving between clips */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => goRelative(-1)} className={btnSecondary}>
              <ChevronLeft className="w-3.5 h-3.5" /> Previous
            </button>
            <button type="button" onClick={() => goRelative(1)} className={btnSecondary}>
              Next <ChevronRight className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={goNextUnreviewed}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-700 text-white text-xs font-semibold shadow-xs"
            >
              <SkipForward className="w-3.5 h-3.5" /> Next unreviewed
            </button>
          </div>
          <p className="text-[11px] text-slate-500">
            Shortcuts: <kbd className="rounded border border-slate-300 bg-slate-50 px-1 font-mono">A</kbd> approve ·{' '}
            <kbd className="rounded border border-slate-300 bg-slate-50 px-1 font-mono">R</kbd> reject ·{' '}
            <kbd className="rounded border border-slate-300 bg-slate-50 px-1 font-mono">N</kbd> re-trim ·{' '}
            <kbd className="rounded border border-slate-300 bg-slate-50 px-1 font-mono">←</kbd>{' '}
            <kbd className="rounded border border-slate-300 bg-slate-50 px-1 font-mono">→</kbd> move
          </p>
        </div>

        {/* Selected Candidate Summary */}
        {current && (
          <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-bold text-slate-900 text-sm">{current.episode} ({current.clipStart}s–{current.clipEnd}s)</span>
              <span className="text-rose-600 font-black">Hybrid: {current.hybridScore} / 100</span>
            </div>

            <div className="space-y-1">
              <span className="text-emerald-800 font-semibold">Opening Hook (0–3s): </span>
              <p className="text-slate-700 italic">"{unquote(current.hook) || '—'}"</p>
            </div>

            <div className="space-y-1">
              <span className="text-rose-800 font-semibold">Cliffhanger (Final 5s): </span>
              <p className="text-slate-700 italic">"{unquote(current.cliffhanger) || '—'}"</p>
            </div>

            <div className="flex flex-wrap gap-2 pt-1">
              {onOpenExplorer && (
                <button type="button" onClick={() => onOpenExplorer(current)} className={btnSecondary}>
                  <Film className="w-3.5 h-3.5" /> Open in Explorer
                </button>
              )}
              {onOpenSimulator && (
                <button type="button" onClick={() => onOpenSimulator(current)} className={btnSecondary}>
                  <Play className="w-3.5 h-3.5 fill-current" /> Preview in phone
                </button>
              )}
            </div>

            {currentReview && (
              <div className="pt-2 border-t border-slate-200 flex flex-wrap items-center justify-between gap-2 text-[11px]">
                <span className="text-slate-500">
                  Current Saved Status
                  {currentReview.reviewedAt && ` · ${new Date(currentReview.reviewedAt).toLocaleString()}`}:
                </span>
                <span className="font-bold text-emerald-700">{currentReview.status}</span>
              </div>
            )}
          </div>
        )}

        {/* The reviewer can read the clip without leaving the page */}
        {current && (
          <details className="rounded-xl border border-slate-200 bg-white">
            <summary className="flex cursor-pointer select-none items-center gap-1.5 px-4 py-2.5 text-xs font-semibold text-slate-700">
              <FileText className="w-3.5 h-3.5 text-slate-400" /> Screenplay excerpt
            </summary>
            <pre className="max-h-56 select-text overflow-y-auto whitespace-pre-wrap border-t border-slate-200 bg-slate-50 p-3.5 font-mono text-[11px] leading-relaxed text-slate-800">
              {current.fullTranscript}
            </pre>
          </details>
        )}

        {/* Decision Buttons */}
        <div className="space-y-2">
          <span id="verdict-label" className="block text-xs font-semibold text-slate-700">
            Editorial Verdict:
          </span>
          <div role="radiogroup" aria-labelledby="verdict-label" className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {VERDICTS.map((btn) => {
              const Icon = btn.icon;
              const isSelected = decision === btn.id;
              return (
                <button
                  key={btn.id}
                  type="button"
                  role="radio"
                  aria-checked={isSelected}
                  onClick={() => {
                    // Clicking a verdict saves it right away (with the notes typed so far).
                    setDecision(btn.id);
                    persistReviews({ ...reviews, [current.id]: buildReview(btn.id, notes) });
                    setSavedNote(`Saved: ${btn.id}`);
                  }}
                  className={`p-3.5 rounded-xl border text-xs font-bold flex flex-col items-center justify-center gap-1.5 transition-all ${
                    isSelected ? btn.activeClass : btn.inactiveClass
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span>{btn.label}</span>
                </button>
              );
            })}
          </div>
          {!decision && <p className="text-[11px] text-slate-400">Click a verdict (or press A / R / N) to save this clip.</p>}
        </div>

        {/* Notes Textarea */}
        <div className="space-y-1.5">
          <label htmlFor="review-notes" className="text-xs font-semibold text-slate-700">
            Editorial Trimming & Mix Notes:
          </label>
          <textarea
            id="review-notes"
            rows="3"
            placeholder="e.g., Pad lead-in by 1.2s to prevent cutting speaker line; cut music track on last word..."
            value={notes}
            onChange={(e) => {
              setNotes(e.target.value);
              setSavedNote('');
            }}
            className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:bg-white focus:outline-none focus:border-rose-500 transition-colors"
          />
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleSaveReview}
              disabled={!decision}
              title={decision ? 'Save this verdict' : 'Choose a verdict first'}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold shadow-md shadow-rose-600/20 transition-all disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-rose-600"
            >
              <Save className="w-4 h-4" /> Save Review Decision
            </button>
            {dirty ? (
              <span role="status" className="text-xs font-semibold text-amber-700">
                Unsaved changes
              </span>
            ) : (
              savedNote && (
                <span role="status" className="text-xs font-semibold text-emerald-700">
                  {savedNote}
                </span>
              )
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={importInputRef}
              type="file"
              accept="application/json,.json"
              onChange={handleImportReviewsJson}
              className="hidden"
              aria-label="Import reviews backup file"
            />
            <button type="button" onClick={() => importInputRef.current?.click()} className={btnSecondary}>
              <Upload className="w-3.5 h-3.5" /> Import Backup (JSON)
            </button>
            {allSavedCount > 0 && (
              <button type="button" onClick={handleExportReviewsJson} className={btnSecondary}>
                <Download className="w-3.5 h-3.5" /> Backup Reviews (JSON)
              </button>
            )}
            {viewReviews.length > 0 && (
              <button type="button" onClick={handleExportReviewsCsv} className={btnSecondary}>
                <Download className="w-3.5 h-3.5" /> Export Reviewed CSV ({viewReviews.length})
              </button>
            )}
          </div>
        </div>
        {importMsg && (
          <p role="status" className="text-[11px] font-medium text-slate-600">
            {importMsg}
          </p>
        )}
      </div>
    </div>
  );
}
