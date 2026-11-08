import React, { useState, useMemo, useEffect } from 'react';
import EmptyState from './EmptyState';
import { unquote } from '../utils/text';
import { secondsToTimecode } from '../utils/nleExport';
import { Search, Play, Sparkles, AlertOctagon, Clock, FileText, Zap, Copy, Check, SplitSquareVertical } from 'lucide-react';

const FILTER_KEY = 'kuku_explorer_filters';
const DEFAULT_FILTERS = {
  searchTerm: '',
  selectedEpisode: 'ALL',
  minScore: 0,
  complianceFilter: 'ALL',
  promisingOnly: false,
  sortBy: 'rank',
};

// Filters survive a refresh (per browser tab), so a reviewer does not have to set them up again.
function loadFilters() {
  try {
    return { ...DEFAULT_FILTERS, ...JSON.parse(sessionStorage.getItem(FILTER_KEY) || '{}') };
  } catch {
    return DEFAULT_FILTERS;
  }
}

function CopyButton({ text, label }) {
  const [done, setDone] = useState(false);
  const copy = async (e) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
    }
    setDone(true);
    setTimeout(() => setDone(false), 1500);
  };
  return (
    <button
      type="button"
      onClick={copy}
      title={label}
      aria-label={label}
      className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 hover:bg-slate-100 hover:text-slate-800"
    >
      {done ? <Check className="h-3 w-3 text-emerald-600" /> : <Copy className="h-3 w-3" />}
      {done && <span className="text-emerald-700">Copied</span>}
    </button>
  );
}

export default function ExplorerTab({
  candidates,
  selectedCandidate,
  onSelectCandidate,
  onOpenSimulator,
  onOpenReview,
  onCompare,
  onEvaluateCandidate,
  onBatchEvaluate,
  isEvaluating,
}) {
  const [saved] = useState(loadFilters);
  const [searchTerm, setSearchTerm] = useState(saved.searchTerm);
  const [selectedEpisode, setSelectedEpisode] = useState(saved.selectedEpisode);
  const [minScore, setMinScore] = useState(saved.minScore);
  const [complianceFilter, setComplianceFilter] = useState(saved.complianceFilter);
  const [promisingOnly, setPromisingOnly] = useState(saved.promisingOnly);
  const [sortBy, setSortBy] = useState(saved.sortBy);

  useEffect(() => {
    try {
      sessionStorage.setItem(
        FILTER_KEY,
        JSON.stringify({ searchTerm, selectedEpisode, minScore, complianceFilter, promisingOnly, sortBy })
      );
    } catch {
      /* storage may be unavailable; filters just won't be remembered */
    }
  }, [searchTerm, selectedEpisode, minScore, complianceFilter, promisingOnly, sortBy]);

  const complianceCounts = useMemo(
    () => candidates.reduce((acc, c) => ({ ...acc, [c.compliance]: (acc[c.compliance] || 0) + 1 }), {}),
    [candidates]
  );

  // Unique episodes
  const episodes = useMemo(() => {
    const eps = Array.from(new Set(candidates.map((c) => c.episode)));
    return ['ALL', ...eps.sort((a, b) => {
      const numA = parseInt(a.replace(/\D/g, '') || 0);
      const numB = parseInt(b.replace(/\D/g, '') || 0);
      return numA - numB;
    })];
  }, [candidates]);

  const episodeFilter = episodes.includes(selectedEpisode) ? selectedEpisode : 'ALL';

  // Filtered & sorted candidates
  const filtered = useMemo(() => {
    return candidates
      .filter((c) => {
        if (episodeFilter !== 'ALL' && c.episode !== episodeFilter) return false;
        if (c.hybridScore < minScore) return false;
        if (complianceFilter !== 'ALL' && c.compliance !== complianceFilter) return false;
        if (promisingOnly && !c.isPromising) return false;
        if (searchTerm) {
          const q = searchTerm.toLowerCase();
          const matchEp = c.episode.toLowerCase().includes(q);
          const matchTranscript = c.fullTranscript.toLowerCase().includes(q);
          const matchHook = (c.hook || '').toLowerCase().includes(q);
          const matchCliff = (c.cliffhanger || '').toLowerCase().includes(q);
          if (!matchEp && !matchTranscript && !matchHook && !matchCliff) return false;
        }
        return true;
      })
      .sort((a, b) => {
        if (sortBy === 'rank') return (a.rank || 999) - (b.rank || 999);
        if (sortBy === 'score_desc') return b.hybridScore - a.hybridScore;
        if (sortBy === 'gemini_desc') return (b.geminiScore ?? -1) - (a.geminiScore ?? -1);
        if (sortBy === 'duration_asc') return a.duration - b.duration;
        return 0;
      });
  }, [candidates, episodeFilter, minScore, complianceFilter, promisingOnly, searchTerm, sortBy]);

  const filtersActive =
    Boolean(searchTerm) || episodeFilter !== 'ALL' || minScore > 0 || complianceFilter !== 'ALL' || promisingOnly || sortBy !== 'rank';
  const resetFilters = () => {
    setSearchTerm('');
    setSelectedEpisode('ALL');
    setMinScore(0);
    setComplianceFilter('ALL');
    setPromisingOnly(false);
    setSortBy('rank');
  };

  const activeCandidate = selectedCandidate || filtered[0] || candidates[0];

  // Up/Down arrows move through the leaderboard, keeping keyboard focus on the chosen card.
  const handleListKeyDown = (e) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    const idx = filtered.findIndex((c) => c.id === activeCandidate?.id);
    const next = filtered[Math.min(filtered.length - 1, Math.max(0, idx + (e.key === 'ArrowDown' ? 1 : -1)))];
    if (!next) return;
    e.preventDefault();
    const list = e.currentTarget;
    onSelectCandidate(next);
    requestAnimationFrame(() => list.querySelector(`[data-cid="${CSS.escape(next.id)}"]`)?.focus());
  };

  if (!candidates.length) {
    return (
      <EmptyState icon={Search} title="No promos to explore">
        There are no candidates in this view yet.
      </EmptyState>
    );
  }

  return (
    <div className="space-y-6">
      {/* Search and Filters Bar */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-xs">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-center">
          {/* Search Input */}
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              aria-label="Search dialogue and characters"
              placeholder="Search dialogues, characters..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:bg-white focus:outline-none focus:border-rose-500 transition-colors"
            />
          </div>

          {/* Episode Select */}
          <div>
            <select
              aria-label="Episode"
              value={episodeFilter}
              onChange={(e) => setSelectedEpisode(e.target.value)}
              className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-rose-500"
            >
              <option value="ALL">All {episodes.length - 1} Episodes</option>
              {episodes.filter((ep) => ep !== 'ALL').map((ep) => (
                <option key={ep} value={ep}>{ep}</option>
              ))}
            </select>
          </div>

          {/* Score Slider */}
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-slate-500 font-medium whitespace-nowrap">Min Score:</span>
            <input
              type="range"
              min="0"
              max="100"
              aria-label="Minimum score"
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              className="w-full accent-rose-600 cursor-pointer"
            />
            <span className="text-xs font-bold text-rose-600 min-w-[28px]">{minScore}</span>
          </div>

          {/* Compliance Filter */}
          <div>
            <select
              aria-label="Compliance"
              value={complianceFilter}
              onChange={(e) => setComplianceFilter(e.target.value)}
              className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-rose-500"
            >
              <option value="ALL">All Compliance</option>
              <option value="PASS">PASS Only ({complianceCounts.PASS || 0})</option>
              <option value="PARTIAL">PARTIAL ({complianceCounts.PARTIAL || 0})</option>
              <option value="FAIL">FAIL ({complianceCounts.FAIL || 0})</option>
              <option value="UNVERIFIED">UNVERIFIED ({complianceCounts.UNVERIFIED || 0})</option>
            </select>
          </div>

          {/* Sort & Promising Toggle */}
          <div className="flex items-center gap-2">
            <select
              aria-label="Sort order"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-rose-500"
            >
              <option value="rank">Sort by Rank</option>
              <option value="score_desc">Hybrid Score (High to Low)</option>
              <option value="gemini_desc">Gemini Score (High to Low)</option>
              <option value="duration_asc">Shortest Duration</option>
            </select>
          </div>
        </div>

        {/* Filter stats & pills */}
        <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <div className="flex items-center gap-3">
            <span>Showing <strong className="text-slate-900">{filtered.length}</strong> of {candidates.length} candidates</span>
            <label className="flex items-center gap-1.5 cursor-pointer text-slate-600 hover:text-slate-900 font-medium">
              <input
                type="checkbox"
                checked={promisingOnly}
                onChange={(e) => setPromisingOnly(e.target.checked)}
                className="rounded accent-rose-600"
              />
              <span className="text-[11px]">Promising Only</span>
            </label>
          </div>

          {filtersActive && (
            <button
              type="button"
              onClick={resetFilters}
              className="text-rose-600 hover:text-rose-700 text-[11px] font-semibold"
            >
              Reset filters
            </button>
          )}
        </div>
      </div>

      {/* Main Split Layout: Cards on Left, Detail on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Candidate List (Left 5 Cols) */}
        <div className="lg:col-span-5 space-y-3 max-h-[850px] overflow-y-auto pr-1">
          {/* List Header with Batch AI Button */}
          <div className="flex items-center justify-between pb-1 px-1">
            <span className="text-xs font-bold text-slate-700">
              Candidate Leaderboard ({filtered.length})
            </span>
            {onBatchEvaluate && (
              <button
                type="button"
                onClick={() => onBatchEvaluate(filtered.slice(0, 5))}
                disabled={isEvaluating || filtered.length === 0}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-300 text-[11px] font-semibold transition-all disabled:opacity-50 shadow-xs"
              >
                <Zap className="w-3 h-3 text-amber-600" />
                <span>Batch AI Top 5</span>
              </button>
            )}
          </div>

          {filtered.length === 0 ? (
            <div className="text-center py-12 bg-white border border-slate-200 rounded-2xl text-slate-500 text-xs shadow-xs">
              No candidates match your current filter settings.
            </div>
          ) : (
            <div className="space-y-3" onKeyDown={handleListKeyDown}>
            {filtered.map((c) => {
              const isSelected = activeCandidate?.id === c.id;
              return (
                <button
                  type="button"
                  key={c.id}
                  data-cid={c.id}
                  aria-pressed={isSelected}
                  onClick={() => onSelectCandidate(c)}
                  className={`block w-full text-left p-4 rounded-xl border transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-rose-50/70 border-rose-300 shadow-sm ring-1 ring-rose-200'
                      : 'bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/70 shadow-xs'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        isSelected ? 'bg-rose-600 text-white' : 'bg-slate-100 text-slate-700'
                      }`}>
                        #{c.rank}
                      </span>
                      <span className="font-bold text-xs text-slate-900">{c.episode}</span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-extrabold text-emerald-600">{c.hybridScore}</span>
                      <span className="text-[10px] text-slate-400">score</span>
                    </div>
                  </div>

                  <div className="text-xs text-slate-500 mb-2 flex items-center justify-between">
                    <span>{c.clipStart}s – {c.clipEnd}s ({c.duration}s)</span>
                    <span className={`px-2 py-0.2 rounded-full text-[10px] font-bold border ${
                      c.compliance === 'PASS'
                        ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                        : c.compliance === 'UNVERIFIED'
                        ? 'text-slate-600 bg-slate-50 border-slate-200'
                        : 'text-amber-700 bg-amber-50 border-amber-200'
                    }`}>
                      {c.compliance}
                    </span>
                  </div>

                  <p className="text-xs text-slate-600 line-clamp-2 italic leading-relaxed">
                    "{unquote(c.whyItWorks || c.hook)}"
                  </p>
                </button>
              );
            })}
            </div>
          )}
        </div>

        {/* Detailed Candidate Inspector (Right 7 Cols) */}
        {activeCandidate && (
          <div className="lg:col-span-7 bg-white border border-slate-200/90 rounded-2xl p-6 space-y-6 shadow-xs sticky top-28">
            {/* Candidate Header */}
            <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-100">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-50 text-rose-700 border border-rose-200">
                    Rank #{activeCandidate.rank}
                  </span>
                  <span className="text-xs text-slate-500">· {activeCandidate.episodeFile}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <h2 className="text-xl font-extrabold text-slate-900">
                    {activeCandidate.episode} ({activeCandidate.clipStart}s – {activeCandidate.clipEnd}s)
                  </h2>
                  <CopyButton
                    label="Copy timecode"
                    text={`${activeCandidate.episode}  ${secondsToTimecode(activeCandidate.clipStart, 24)} – ${secondsToTimecode(activeCandidate.clipEnd, 24)}  (${activeCandidate.clipStart}s–${activeCandidate.clipEnd}s, ${activeCandidate.duration}s)`}
                  />
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex flex-wrap items-center gap-2">
                {/* Gemini AI Live Evaluation Trigger */}
                <button
                  type="button"
                  onClick={() => onEvaluateCandidate(activeCandidate)}
                  disabled={isEvaluating}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold shadow-sm shadow-amber-500/20 transition-all disabled:opacity-50"
                >
                  <Sparkles className={`w-3.5 h-3.5 ${isEvaluating ? 'animate-spin' : ''}`} />
                  <span>{isEvaluating ? 'Evaluating with AI...' : 'Evaluate with AI'}</span>
                </button>

                <button
                  type="button"
                  onClick={() => onOpenSimulator(activeCandidate)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold shadow-xs transition-all"
                >
                  <Play className="w-3.5 h-3.5 fill-current" /> Vertical Player
                </button>

                <button
                  type="button"
                  onClick={() => onOpenReview(activeCandidate)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 text-xs font-medium transition-all"
                >
                  Review
                </button>

                {onCompare && (
                  <button
                    type="button"
                    onClick={() => onCompare(activeCandidate)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 text-xs font-medium transition-all"
                  >
                    <SplitSquareVertical className="w-3.5 h-3.5" /> Compare
                  </button>
                )}
              </div>
            </div>

            {/* Score Grid */}
            <div className="grid grid-cols-4 gap-3 bg-slate-50 p-4 rounded-xl border border-slate-200/80 text-center">
              <div>
                <div className="text-[10px] uppercase text-slate-500 font-bold tracking-wider">Hybrid Score</div>
                <div className="text-xl font-black text-rose-600 mt-0.5">{activeCandidate.hybridScore}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-500 font-bold tracking-wider">Gemini LLM</div>
                <div className="text-xl font-bold text-amber-600 mt-0.5" title={activeCandidate.geminiScore == null ? 'Not judged by a model yet' : undefined}>
                  {activeCandidate.geminiScore ?? '—'}
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-500 font-bold tracking-wider">Local Heuristic</div>
                <div className="text-xl font-bold text-slate-700 mt-0.5">{activeCandidate.localScore}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-500 font-bold tracking-wider">Compliance</div>
                <div className={`text-sm font-extrabold mt-1.5 ${
                  activeCandidate.compliance === 'PASS'
                    ? 'text-emerald-700'
                    : activeCandidate.compliance === 'UNVERIFIED'
                    ? 'text-slate-500'
                    : 'text-amber-700'
                }`}>
                  {activeCandidate.compliance}
                </div>
              </div>
            </div>

            {/* Pacing & Timeline Bar */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-slate-800 flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-slate-400" />
                  Pacing & Clip Cadence
                </span>
                <span className="text-slate-500">
                  {activeCandidate.wordCount} words · <strong className="text-slate-900">{activeCandidate.wpm} WPM</strong>
                  {activeCandidate.wpm >= 90 && activeCandidate.wpm <= 165 && (
                    <span className="text-emerald-600 font-semibold ml-1.5">(Optimal Vertical Pace)</span>
                  )}
                </span>
              </div>

              {/* Segmented Timeline */}
              <div className="w-full h-3 rounded-full bg-slate-100 overflow-hidden flex border border-slate-200">
                <div
                  className="bg-emerald-500 h-full transition-all"
                  style={{ width: `${(3 / activeCandidate.duration) * 100}%` }}
                  title="Opening Hook Window (0-3s)"
                />
                <div
                  className="bg-blue-500 h-full transition-all"
                  style={{ width: `${((activeCandidate.duration - 8) / activeCandidate.duration) * 100}%` }}
                  title="Conflict Escalation Window"
                />
                <div
                  className="bg-rose-500 h-full transition-all"
                  style={{ width: `${(5 / activeCandidate.duration) * 100}%` }}
                  title="Closing Cliffhanger Window (Final 5s)"
                />
              </div>

              <div className="flex justify-between text-[10px] text-slate-500 font-medium">
                <span className="text-emerald-700">● 0-3s Hook</span>
                <span className="text-blue-600">● Narrative Progression</span>
                <span className="text-rose-600">● Final 5s Cliffhanger</span>
              </div>
            </div>

            {/* Hook & Cliffhanger Editorial Details */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-emerald-50/60 border border-emerald-200 rounded-xl p-3.5">
                <div className="text-xs font-bold text-emerald-800 flex items-center justify-between mb-1">
                  <span>Opening Hook</span>
                  <span className="flex items-center gap-1">
                    <span className="text-[10px] text-slate-500 font-mono">t = {activeCandidate.hookTimestamp ?? 0}s</span>
                    <CopyButton label="Copy hook" text={unquote(activeCandidate.hook)} />
                  </span>
                </div>
                <p className="text-xs text-slate-700 italic">
                  "{unquote(activeCandidate.hook) || 'Immediate dramatic entry'}"
                </p>
              </div>

              <div className="bg-rose-50/60 border border-rose-200 rounded-xl p-3.5">
                <div className="text-xs font-bold text-rose-800 flex items-center justify-between mb-1">
                  <span>Unresolved Cliffhanger</span>
                  <span className="flex items-center gap-1">
                    <span className="text-[10px] text-slate-500 font-mono">t = {activeCandidate.cliffhangerTimestamp ?? activeCandidate.clipEnd}s</span>
                    <CopyButton label="Copy cliffhanger" text={unquote(activeCandidate.cliffhanger)} />
                  </span>
                </div>
                <p className="text-xs text-slate-700 italic">
                  "{unquote(activeCandidate.cliffhanger) || 'Cut before tension resolves'}"
                </p>
              </div>
            </div>

            {/* Gemini 5 Dimension Bars */}
            <div className="space-y-2 pt-2">
              <div className="text-xs font-semibold text-slate-800">Gemini Editorial Dimensions (1–10)</div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-xs">
                {[
                  { label: 'Hook Impact', val: activeCandidate.hookScore },
                  { label: 'Cliffhanger Tension', val: activeCandidate.cliffhangerScore },
                  { label: 'Emotional Stakes', val: activeCandidate.emotionalScore },
                  { label: 'Standalone Context', val: activeCandidate.standaloneScore },
                  { label: 'Narrative Arc', val: activeCandidate.progressionScore },
                ].map((item) => (
                  <div key={item.label} className="space-y-1">
                    <div className="flex justify-between text-[11px] text-slate-500">
                      <span>{item.label}</span>
                      <span className="font-bold text-slate-800">{item.val} / 10</span>
                    </div>
                    <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden border border-slate-200">
                      <div
                        className="h-full bg-gradient-to-r from-rose-500 to-amber-500 rounded-full"
                        style={{ width: `${(item.val / 10) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Standalone Context & Why It Works */}
            <div className="text-xs space-y-2 bg-slate-50 p-3.5 rounded-xl border border-slate-200/80">
              <div>
                <span className="font-semibold text-slate-900">Why It Works: </span>
                <span className="text-slate-600">{activeCandidate.whyItWorks || 'High dramatic conversion.'}</span>
              </div>
              <div>
                <span className="font-semibold text-slate-900">Standalone Viewer Context: </span>
                <span className="text-slate-600">{activeCandidate.standaloneContext || 'Immediate clarity.'}</span>
              </div>
            </div>

            {/* Screenplay Transcript Accordion */}
            <div className="space-y-1">
              <div className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-slate-400" /> Screenplay Excerpt Transcript
              </div>
              <div className="max-h-52 overflow-y-auto bg-slate-50 p-3.5 rounded-xl border border-slate-200 text-[11px] font-mono leading-relaxed text-slate-800 whitespace-pre-wrap select-text">
                {activeCandidate.fullTranscript}
              </div>
            </div>

            {/* Risks Box */}
            {activeCandidate.risks && activeCandidate.risks.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-3.5 text-xs space-y-1">
                <div className="flex items-center gap-1.5 text-amber-800 font-semibold">
                  <AlertOctagon className="w-3.5 h-3.5 text-amber-600" /> Editorial Caveats & Risks
                </div>
                <ul className="list-disc list-inside text-amber-900 text-[11px] space-y-0.5">
                  {activeCandidate.risks.map((risk, idx) => (
                    <li key={idx}>{risk}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
