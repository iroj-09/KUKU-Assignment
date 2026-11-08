import React from 'react';
import EmptyState from './EmptyState';
import { unquote } from '../utils/text';
import { Trophy, TrendingUp, CheckCircle2, ArrowRight, Flame, Sparkles } from 'lucide-react';

export default function OverviewTab({ candidates, onSelectCandidate, setActiveTab, showTitle }) {
  // "Title. Subtitle" renders with the second sentence highlighted.
  const rawTitle = showTitle || 'Promo results';
  const cut = rawTitle.indexOf('. ');
  const titleHead = cut > 0 ? rawTitle.slice(0, cut + 1) : rawTitle;
  const titleTail = cut > 0 ? rawTitle.slice(cut + 2) : '';

  if (!candidates.length) {
    return (
      <EmptyState
        icon={Sparkles}
        title="Nothing to show yet"
        action={
          <button
            type="button"
            onClick={() => setActiveTab('upload')}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold shadow-md shadow-rose-600/20"
          >
            Upload a drama
          </button>
        }
      >
        There are no promos in this view. Upload screenplay files, or restore the saved results.
      </EmptyState>
    );
  }

  const top10 = candidates.slice(0, 10);
  const passCount = candidates.filter((c) => c.compliance === 'PASS').length;
  const partialCount = candidates.filter((c) => c.compliance === 'PARTIAL').length;
  const failCount = candidates.filter((c) => c.compliance === 'FAIL').length;
  const unverifiedCount = candidates.filter((c) => c.compliance === 'UNVERIFIED').length;
  const episodeCount = new Set(candidates.map((c) => c.episode)).size;
  const avgGemini = (candidates.reduce((acc, c) => acc + (c.geminiScore || 0), 0) / candidates.length).toFixed(1);
  const promisingCount = candidates.filter((c) => c.isPromising).length;

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Hero Banner */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-rose-50 via-white to-amber-50/50 border border-rose-200/80 p-6 sm:p-8 shadow-xs">
        <div className="relative z-10 max-w-3xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-rose-100/80 border border-rose-200 text-rose-800 text-xs font-semibold mb-4">
            <Sparkles className="w-3.5 h-3.5 text-rose-600" />
            Microdrama Screenplay Promo Engine · {episodeCount} Episode{episodeCount === 1 ? '' : 's'}
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
            {titleHead}
            {titleTail && (
              <>
                {' '}
                <span className="bg-gradient-to-r from-rose-600 via-rose-500 to-amber-600 bg-clip-text text-transparent">
                  {titleTail}
                </span>
              </>
            )}
          </h1>
          <p className="mt-2 text-sm text-slate-600 leading-relaxed">
            AI-driven discovery identifying 20–60s high-conversion promo windows with instant 0–3s hooks, escalating tension, and unresolved cliffhangers.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <button
              onClick={() => setActiveTab('explorer')}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold shadow-md shadow-rose-600/20 transition-all hover:scale-[1.01]"
            >
              Explore All {candidates.length} Candidates <ArrowRight className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setActiveTab('export')}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 text-xs font-semibold shadow-xs transition-all"
            >
              Export DaVinci & Premiere Markers
            </button>
          </div>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white border border-slate-200/80 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 text-xs mb-1">
            <span>Shortlist Funnel</span>
            {candidates[0]?.showWindows && (
              <span className="text-rose-600 font-bold">
                {Number(candidates[0].showWindows).toLocaleString('en-US')} → {candidates.length}
              </span>
            )}
          </div>
          <div className="text-2xl font-extrabold text-slate-900">{candidates.length} <span className="text-xs font-normal text-slate-500">clips</span></div>
          <div className="text-[11px] text-slate-500 mt-1">Across {episodeCount} episode{episodeCount === 1 ? '' : 's'}</div>
        </div>

        <div className="bg-white border border-slate-200/80 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 text-xs mb-1">
            <span>Average Gemini Score</span>
            <TrendingUp className="w-3.5 h-3.5 text-amber-500" />
          </div>
          <div className="text-2xl font-extrabold text-amber-600">{avgGemini} <span className="text-xs font-normal text-slate-500">/ 100</span></div>
          <div className="text-[11px] text-slate-500 mt-1">Editorial rubric evaluation</div>
        </div>

        <div className="bg-white border border-slate-200/80 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 text-xs mb-1">
            <span>Promising Verdict</span>
            <Flame className="w-3.5 h-3.5 text-rose-500" />
          </div>
          <div className="text-2xl font-extrabold text-emerald-600">{promisingCount} <span className="text-xs font-normal text-slate-500">/ {candidates.length}</span></div>
          <div className="text-[11px] text-slate-500 mt-1">{((promisingCount / candidates.length) * 100).toFixed(1)}% AI recommendation rate</div>
        </div>

        <div className="bg-white border border-slate-200/80 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 text-xs mb-1">
            <span>Timestamp Compliance</span>
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs font-bold text-emerald-700">{passCount} PASS</span>
            <span className="text-xs text-amber-700 font-semibold">{partialCount} PARTIAL</span>
            <span className="text-xs text-rose-700 font-semibold">{failCount} FAIL</span>
            {unverifiedCount > 0 && (
              <span className="text-xs text-slate-500 font-semibold">{unverifiedCount} UNVERIFIED</span>
            )}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">Hook ≤ 3s & Cliffhanger ≥ end-5s</div>
        </div>
      </div>

      {/* Top 3 Podium Cards */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Trophy className="w-4 h-4 text-amber-500" />
            Top 3 Recommended Promo Hooks
          </h2>
          <span className="text-xs text-slate-500">Weighted 70% Gemini + 30% Local Heuristic</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {top10.slice(0, 3).map((candidate, idx) => {
            const podiumThemes = [
              'bg-gradient-to-br from-amber-50 via-white to-amber-100/30 border-amber-300 text-amber-950',
              'bg-gradient-to-br from-slate-50 via-white to-slate-100/50 border-slate-300 text-slate-900',
              'bg-gradient-to-br from-orange-50 via-white to-orange-100/30 border-orange-300 text-orange-950',
            ];
            return (
              <button
                type="button"
                key={candidate.id}
                onClick={() => onSelectCandidate(candidate)}
                className={`group block w-full text-left cursor-pointer rounded-2xl ${podiumThemes[idx]} border p-5 transition-all hover:scale-[1.02] hover:shadow-md shadow-xs`}
              >
                <div className="flex items-center justify-between mb-3">
                  <span className="px-2.5 py-0.5 rounded-full text-[11px] font-extrabold bg-white border border-slate-200 text-slate-800 shadow-xs">
                    Rank #{candidate.rank}
                  </span>
                  <div className="text-right">
                    <span className="text-sm font-extrabold text-slate-900">{candidate.hybridScore}</span>
                    <span className="text-[10px] text-slate-500"> / 100</span>
                  </div>
                </div>

                <div className="text-sm font-bold text-slate-900 group-hover:text-rose-600 transition-colors">
                  {candidate.episode}
                </div>
                <div className="text-xs text-slate-500 mb-3">
                  {candidate.clipStart}s – {candidate.clipEnd}s ({candidate.duration}s clip)
                </div>

                <p className="text-xs text-slate-600 line-clamp-2 italic mb-4 leading-relaxed">
                  "{unquote(candidate.whyItWorks || candidate.hook)}"
                </p>

                <div className="pt-3 border-t border-slate-200/80 flex items-center justify-between text-[11px]">
                  <span className="text-slate-500 font-medium">Cliffhanger:</span>
                  <span className="font-semibold text-rose-700 truncate max-w-[150px]">
                    {candidate.cliffhanger || 'Unresolved reveal'}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Top 10 Table */}
      <div className="bg-white border border-slate-200/90 rounded-2xl overflow-hidden shadow-xs">
        <div className="p-4 border-b border-slate-200/80 bg-slate-50/50 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-900">Top 10 Shortlist for Editorial Review</h3>
          <span className="text-xs text-slate-500">Click any row to inspect & review</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 uppercase text-[10px] font-semibold tracking-wider border-b border-slate-200/80">
              <tr>
                <th className="py-3 px-4">Rank</th>
                <th className="py-3 px-4">Episode</th>
                <th className="py-3 px-4">Window</th>
                <th className="py-3 px-4">Duration</th>
                <th className="py-3 px-4">Hybrid</th>
                <th className="py-3 px-4">Gemini</th>
                <th className="py-3 px-4">Compliance</th>
                <th className="py-3 px-4">Hook Highlight</th>
                <th className="py-3 px-4">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {top10.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => onSelectCandidate(c)}
                  className="hover:bg-rose-50/40 cursor-pointer transition-colors"
                >
                  <td className="py-3.5 px-4 font-bold text-slate-900">#{c.rank}</td>
                  <td className="py-3.5 px-4 font-medium text-slate-800">{c.episode}</td>
                  <td className="py-3.5 px-4 text-slate-600 font-mono text-[11px]">{c.clipStart}s–{c.clipEnd}s</td>
                  <td className="py-3.5 px-4 text-slate-600">{c.duration}s</td>
                  <td className="py-3.5 px-4 font-extrabold text-emerald-600">{c.hybridScore}</td>
                  <td className="py-3.5 px-4 font-bold text-amber-600">{c.geminiScore}</td>
                  <td className="py-3.5 px-4">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                      c.compliance === 'PASS'
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                        : c.compliance === 'PARTIAL'
                        ? 'bg-amber-50 text-amber-700 border-amber-200'
                        : c.compliance === 'UNVERIFIED'
                        ? 'bg-slate-50 text-slate-600 border-slate-200'
                        : 'bg-rose-50 text-rose-700 border-rose-200'
                    }`}>
                      {c.compliance}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 text-slate-600 max-w-xs truncate">{c.hook || c.whyItWorks}</td>
                  <td className="py-3.5 px-4">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectCandidate(c);
                      }}
                      className="text-rose-600 hover:text-rose-700 font-semibold text-xs inline-flex items-center gap-1 hover:underline"
                    >
                      Inspect <ArrowRight className="w-3 h-3" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
