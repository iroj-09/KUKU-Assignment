import React, { useState } from 'react';
import EmptyState from './EmptyState';
import { unquote } from '../utils/text';
import { SplitSquareVertical, Trophy } from 'lucide-react';

export default function CompareTab({ candidates, seed }) {
  // `seed` comes from the Explorer's "Compare" button: that clip as A, and the top pick (or runner-up) as B.
  const known = (id) => (candidates.some((c) => c.id === id) ? id : null);
  const [candidateAId, setCandidateAId] = useState(known(seed?.a) || candidates[0]?.id || '');
  const [candidateBId, setCandidateBId] = useState(known(seed?.b) || candidates[1]?.id || '');

  const candA = candidates.find((c) => c.id === candidateAId) || candidates[0];
  const candB = candidates.find((c) => c.id === candidateBId) || candidates[1];

  const compareMetric = (valA, valB, higherIsBetter = true) => {
    if (valA === valB) return { aWinner: false, bWinner: false };
    const aWon = higherIsBetter ? valA > valB : valA < valB;
    return { aWinner: aWon, bWinner: !aWon };
  };

  const scoreComp = compareMetric(candA?.hybridScore, candB?.hybridScore);
  const hookComp = compareMetric(candA?.hookScore, candB?.hookScore);
  const cliffComp = compareMetric(candA?.cliffhangerScore, candB?.cliffhangerScore);

  if (!candidates.length) {
    return (
      <EmptyState icon={SplitSquareVertical} title="Nothing to compare">
        There are no promos in this view yet.
      </EmptyState>
    );
  }

  return (
    <div className="space-y-6">
      <div className="bg-white border border-slate-200/90 p-5 rounded-2xl shadow-xs flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <SplitSquareVertical className="w-4 h-4 text-rose-600" /> Promo Comparison Battle
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">Compare two candidate promo cuts side-by-side to choose the best version.</p>
        </div>
      </div>

      {/* Selectors */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Cand A Select */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-slate-600">Select Candidate A:</label>
          <select
            value={candidateAId}
            onChange={(e) => setCandidateAId(e.target.value)}
            className="w-full px-3.5 py-2.5 bg-white border border-slate-200 rounded-xl text-xs text-slate-800 shadow-xs focus:outline-none focus:border-rose-500"
          >
            {candidates.map((c) => (
              <option key={c.id} value={c.id}>
                Rank #{c.rank} · {c.episode} ({c.clipStart}–{c.clipEnd}s, Score: {c.hybridScore})
              </option>
            ))}
          </select>
        </div>

        {/* Cand B Select */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-slate-600">Select Candidate B:</label>
          <select
            value={candidateBId}
            onChange={(e) => setCandidateBId(e.target.value)}
            className="w-full px-3.5 py-2.5 bg-white border border-slate-200 rounded-xl text-xs text-slate-800 shadow-xs focus:outline-none focus:border-rose-500"
          >
            {candidates.map((c) => (
              <option key={c.id} value={c.id}>
                Rank #{c.rank} · {c.episode} ({c.clipStart}–{c.clipEnd}s, Score: {c.hybridScore})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Side-by-Side Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Card A */}
        <div className={`p-6 rounded-2xl border space-y-4 transition-all ${
          scoreComp.aWinner
            ? 'bg-rose-50/40 border-rose-300 shadow-sm ring-1 ring-rose-200'
            : 'bg-white border-slate-200/90 shadow-xs'
        }`}>
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200">
                Rank #{candA?.rank}
              </span>
              <h3 className="text-lg font-bold text-slate-900 mt-1">{candA?.episode}</h3>
              <span className="text-xs text-slate-500">{candA?.clipStart}s – {candA?.clipEnd}s ({candA?.duration}s)</span>
            </div>
            <div className="text-right">
              <div className="text-2xl font-black text-rose-600">{candA?.hybridScore}</div>
              <span className="text-[10px] text-slate-400">Hybrid Score</span>
              {scoreComp.aWinner && (
                <div className="text-[10px] font-bold text-emerald-700 flex items-center gap-1 justify-end mt-0.5">
                  <Trophy className="w-3 h-3 text-emerald-600" /> Winner
                </div>
              )}
            </div>
          </div>

          <div className="space-y-2 text-xs">
            <div className="flex justify-between p-2.5 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-slate-500">Gemini LLM Score:</span>
              <span className="font-bold text-slate-900">{candA?.geminiScore == null ? 'not judged' : `${candA.geminiScore} / 100`}</span>
            </div>
            <div className="flex justify-between p-2.5 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-slate-500">Hook Impact:</span>
              <span className={`font-bold ${hookComp.aWinner ? 'text-emerald-700' : 'text-slate-900'}`}>
                {candA?.hookScore} / 10 {hookComp.aWinner && '★'}
              </span>
            </div>
            <div className="flex justify-between p-2.5 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-slate-500">Cliffhanger Tension:</span>
              <span className={`font-bold ${cliffComp.aWinner ? 'text-emerald-700' : 'text-slate-900'}`}>
                {candA?.cliffhangerScore} / 10 {cliffComp.aWinner && '★'}
              </span>
            </div>
            <div className="flex justify-between p-2.5 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-slate-500">Speech Cadence:</span>
              <span className="font-bold text-slate-900">{candA?.wpm} WPM ({candA?.wordCount} words)</span>
            </div>
          </div>

          <div className="space-y-2 pt-2 border-t border-slate-100 text-xs">
            <div>
              <span className="font-bold text-emerald-800">Hook (0–3s): </span>
              <p className="text-slate-700 italic mt-0.5 leading-relaxed">"{unquote(candA?.hook) || '—'}"</p>
            </div>
            <div>
              <span className="font-bold text-rose-800">Cliffhanger (Final 5s): </span>
              <p className="text-slate-700 italic mt-0.5 leading-relaxed">"{unquote(candA?.cliffhanger) || '—'}"</p>
            </div>
          </div>
        </div>

        {/* Card B */}
        <div className={`p-6 rounded-2xl border space-y-4 transition-all ${
          scoreComp.bWinner
            ? 'bg-rose-50/40 border-rose-300 shadow-sm ring-1 ring-rose-200'
            : 'bg-white border-slate-200/90 shadow-xs'
        }`}>
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200">
                Rank #{candB?.rank}
              </span>
              <h3 className="text-lg font-bold text-slate-900 mt-1">{candB?.episode}</h3>
              <span className="text-xs text-slate-500">{candB?.clipStart}s – {candB?.clipEnd}s ({candB?.duration}s)</span>
            </div>
            <div className="text-right">
              <div className="text-2xl font-black text-rose-600">{candB?.hybridScore}</div>
              <span className="text-[10px] text-slate-400">Hybrid Score</span>
              {scoreComp.bWinner && (
                <div className="text-[10px] font-bold text-emerald-700 flex items-center gap-1 justify-end mt-0.5">
                  <Trophy className="w-3 h-3 text-emerald-600" /> Winner
                </div>
              )}
            </div>
          </div>

          <div className="space-y-2 text-xs">
            <div className="flex justify-between p-2.5 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-slate-500">Gemini LLM Score:</span>
              <span className="font-bold text-slate-900">{candB?.geminiScore == null ? 'not judged' : `${candB.geminiScore} / 100`}</span>
            </div>
            <div className="flex justify-between p-2.5 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-slate-500">Hook Impact:</span>
              <span className={`font-bold ${hookComp.bWinner ? 'text-emerald-700' : 'text-slate-900'}`}>
                {candB?.hookScore} / 10 {hookComp.bWinner && '★'}
              </span>
            </div>
            <div className="flex justify-between p-2.5 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-slate-500">Cliffhanger Tension:</span>
              <span className={`font-bold ${cliffComp.bWinner ? 'text-emerald-700' : 'text-slate-900'}`}>
                {candB?.cliffhangerScore} / 10 {cliffComp.bWinner && '★'}
              </span>
            </div>
            <div className="flex justify-between p-2.5 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-slate-500">Speech Cadence:</span>
              <span className="font-bold text-slate-900">{candB?.wpm} WPM ({candB?.wordCount} words)</span>
            </div>
          </div>

          <div className="space-y-2 pt-2 border-t border-slate-100 text-xs">
            <div>
              <span className="font-bold text-emerald-800">Hook (0–3s): </span>
              <p className="text-slate-700 italic mt-0.5 leading-relaxed">"{unquote(candB?.hook) || '—'}"</p>
            </div>
            <div>
              <span className="font-bold text-rose-800">Cliffhanger (Final 5s): </span>
              <p className="text-slate-700 italic mt-0.5 leading-relaxed">"{unquote(candB?.cliffhanger) || '—'}"</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
