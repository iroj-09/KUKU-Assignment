import React, { useState } from 'react';
import { Download, Film, Video, FileText, Layers } from 'lucide-react';
import { generateDaVinciMarkers, generatePremiereMarkers, generateCmxEdl, downloadFile } from '../utils/nleExport';

export default function ExportTab({ candidates, reviews }) {
  const [scope, setScope] = useState('top10');
  const [fps, setFps] = useState(24);

  const ranked = [...(candidates || [])].sort(
    (a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity)
  );
  const approved = ranked.filter((c) => reviews?.[c.id]?.status === 'Approved');

  const getExportData = () => {
    if (scope === 'top10') return ranked.slice(0, 10);
    if (scope === 'approved') return approved;
    return ranked;
  };

  const activeSet = getExportData();

  const handleDownloadDaVinci = () => {
    const csv = generateDaVinciMarkers(activeSet, fps);
    downloadFile(csv, `kuku_davinci_markers_${scope}_${fps}fps.csv`, 'text/csv');
  };

  const handleDownloadPremiere = () => {
    const csv = generatePremiereMarkers(activeSet, fps);
    downloadFile(csv, `kuku_premiere_markers_${scope}_${fps}fps.csv`, 'text/csv');
  };

  const handleDownloadEdl = () => {
    const edl = generateCmxEdl(activeSet, `KUKU_PROMOS_${scope.toUpperCase()}`, fps);
    downloadFile(edl, `kuku_promos_${scope}_${fps}fps.edl`, 'text/plain');
  };

  const handleDownloadJson = () => {
    const jsonStr = JSON.stringify(activeSet, null, 2);
    downloadFile(jsonStr, `kuku_ranked_promos_${scope}.json`, 'application/json');
  };

  const handleDownloadCsv = () => {
    const headers = [
      'rank', 'episode', 'clip_start', 'clip_end', 'duration',
      'hybrid_score', 'gemini_score', 'local_score', 'compliance',
      'hook', 'cliffhanger', 'why_it_works', 'wpm',
      'review_status', 'review_note'
    ];
    // Quote every field, double embedded quotes, and neutralise spreadsheet
    // formulas (=, +, -, @) so opening the CSV in Excel can't execute them.
    const esc = (v) => {
      let s = v == null ? '' : String(v);
      if (/^[=+\-@\t\r]/.test(s) && Number.isNaN(Number(s))) s = `'${s}`;
      return `"${s.replace(/"/g, '""')}"`;
    };
    const rows = [headers];
    activeSet.forEach((c) => {
      const review = reviews?.[c.id];
      rows.push([
        c.rank, c.episode, c.clipStart, c.clipEnd, c.duration,
        c.hybridScore, c.geminiScore, c.localScore, c.compliance,
        c.hook, c.cliffhanger, c.whyItWorks, c.wpm,
        review?.status || 'Pending', review?.note || review?.notes || ''
      ]);
    });
    const csvStr = rows.map((r) => r.map(esc).join(',')).join('\n');
    downloadFile(csvStr, `kuku_promo_ranking_${scope}.csv`, 'text/csv');
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Scope and FPS Configuration */}
      <div className="bg-white border border-slate-200/90 p-5 rounded-2xl shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Download className="w-4 h-4 text-rose-600" /> Export & NLE Delivery Station
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">Download timeline markers for video editors or full analytical datasets.</p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 bg-slate-50 px-3 py-1.5 rounded-xl border border-slate-200 text-xs">
            <span className="text-slate-500">Scope:</span>
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value)}
              className="bg-transparent text-slate-800 font-bold focus:outline-none cursor-pointer"
            >
              <option value="top10">Top 10 Shortlist</option>
              <option value="all">All {ranked.length} Candidates</option>
              <option value="approved">Only Approved Clips ({approved.length})</option>
            </select>
          </div>

          <div className="flex items-center gap-2 bg-slate-50 px-3 py-1.5 rounded-xl border border-slate-200 text-xs">
            <span className="text-slate-500">FPS:</span>
            <select
              value={fps}
              onChange={(e) => setFps(Number(e.target.value))}
              className="bg-transparent text-slate-800 font-bold focus:outline-none cursor-pointer"
            >
              <option value="24">24 fps (Cinema)</option>
              <option value="30">30 fps (Web/Mobile)</option>
              <option value="60">60 fps (Smooth)</option>
            </select>
          </div>
        </div>
      </div>

      <div className="text-xs text-slate-500 px-1">
        Currently exporting: <strong className="text-rose-600 font-bold">{activeSet.length} candidates</strong> at {fps} fps timecode.
        {scope === 'approved' && activeSet.length === 0 && (
          <span className="ml-2 text-amber-600">No approved clips yet. Approve some in the Review tab first.</span>
        )}
      </div>

      {/* Export Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* DaVinci Resolve */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-6 space-y-4 hover:border-cyan-300 hover:shadow-sm transition-all flex flex-col justify-between shadow-xs">
          <div>
            <div className="flex items-center gap-2 text-slate-900 font-bold text-sm mb-1.5">
              <Film className="w-4 h-4 text-cyan-600" /> DaVinci Resolve Timeline Markers
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              Standard marker CSV with In/Out timecodes, color tags (Cyan for top scores, Green for baseline), and hook summaries.
            </p>
          </div>
          <button
            onClick={handleDownloadDaVinci}
            disabled={activeSet.length === 0}
            className="w-full py-2.5 rounded-xl bg-cyan-50 hover:bg-cyan-100 text-cyan-800 border border-cyan-200 text-xs font-bold transition-all flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <Download className="w-3.5 h-3.5" /> Download DaVinci Marker CSV
          </button>
        </div>

        {/* Adobe Premiere Pro */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-6 space-y-4 hover:border-indigo-300 hover:shadow-sm transition-all flex flex-col justify-between shadow-xs">
          <div>
            <div className="flex items-center gap-2 text-slate-900 font-bold text-sm mb-1.5">
              <Video className="w-4 h-4 text-indigo-600" /> Adobe Premiere Pro Marker CSV
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              Import markers directly into the Premiere Pro timeline window. Clips are annotated with hook descriptions.
            </p>
          </div>
          <button
            onClick={handleDownloadPremiere}
            disabled={activeSet.length === 0}
            className="w-full py-2.5 rounded-xl bg-indigo-50 hover:bg-indigo-100 text-indigo-800 border border-indigo-200 text-xs font-bold transition-all flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <Download className="w-3.5 h-3.5" /> Download Premiere Marker CSV
          </button>
        </div>

        {/* CMX 3600 EDL */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-6 space-y-4 hover:border-emerald-300 hover:shadow-sm transition-all flex flex-col justify-between shadow-xs">
          <div>
            <div className="flex items-center gap-2 text-slate-900 font-bold text-sm mb-1.5">
              <FileText className="w-4 h-4 text-emerald-600" /> CMX 3600 Edit Decision List (EDL)
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              Industry-standard sequence list compatible with Avid Media Composer, Final Cut Pro, Premiere, and DaVinci.
            </p>
          </div>
          <button
            onClick={handleDownloadEdl}
            disabled={activeSet.length === 0}
            className="w-full py-2.5 rounded-xl bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200 text-xs font-bold transition-all flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <Download className="w-3.5 h-3.5" /> Download Sequence EDL (.edl)
          </button>
        </div>

        {/* Full Dataset JSON & CSV */}
        <div className="bg-white border border-slate-200/90 rounded-2xl p-6 space-y-4 hover:border-rose-300 hover:shadow-sm transition-all flex flex-col justify-between shadow-xs">
          <div>
            <div className="flex items-center gap-2 text-slate-900 font-bold text-sm mb-1.5">
              <Layers className="w-4 h-4 text-rose-600" /> Analytical JSON & CSV Data
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              Export all candidate records with full screenplay transcripts, risk evaluations, and local/Gemini dimension scores.
            </p>
          </div>
          <div className="flex gap-2.5">
            <button
              onClick={handleDownloadJson}
              disabled={activeSet.length === 0}
              className="flex-1 py-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 text-xs font-bold transition-all flex items-center justify-center gap-1.5 disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5" /> JSON
            </button>
            <button
              onClick={handleDownloadCsv}
              disabled={activeSet.length === 0}
              className="flex-1 py-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 text-xs font-bold transition-all flex items-center justify-center gap-1.5 disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5" /> CSV
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
