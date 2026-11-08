import React, { useState, useEffect, useRef } from 'react';
import EmptyState from './EmptyState';
import { unquote } from '../utils/text';
import { HOOK_WINDOW_SECONDS, CLIFFHANGER_WINDOW_SECONDS } from '../utils/clientParser';
import { Play, Pause, RotateCcw, Volume2, VolumeX, Sparkles, AlertCircle } from 'lucide-react';

// Cinematic Sound Effects via Web Audio API (zero external assets required)
function playCinematicHit() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(130, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(32, ctx.currentTime + 0.65);
    gain.gain.setValueAtTime(0.4, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.65);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.onended = () => ctx.close();
    osc.start();
    osc.stop(ctx.currentTime + 0.7);
  } catch {
    /* sound is optional */
  }
}

function playCliffhangerTension() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(65, ctx.currentTime);
    osc.frequency.linearRampToValueAtTime(180, ctx.currentTime + 1.2);
    gain.gain.setValueAtTime(0.01, ctx.currentTime);
    gain.gain.linearRampToValueAtTime(0.18, ctx.currentTime + 1.0);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 1.3);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.onended = () => ctx.close();
    osc.start();
    osc.stop(ctx.currentTime + 1.4);
  } catch {
    /* sound is optional */
  }
}

export default function SimulatorTab({ candidate, candidates, onSelectCandidate }) {
  const current = candidate || candidates[0];
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [audioEnabled, setAudioEnabled] = useState(true);
  const intervalRef = useRef(null);
  const hitTriggeredRef = useRef(false);
  const cliffTriggeredRef = useRef(false);

  // Parse lines with simulated relative timing
  const lines = React.useMemo(() => {
    if (!current) return [];
    const raw = current.fullTranscript || '';
    const parts = raw.split(/(?=\[[0-9.:-]+\])/g).filter(Boolean);

    return parts.map((part, idx) => {
      const timeMatch = part.match(/\[([0-9.]+)-([0-9.]+)\]/);
      let text = part.replace(/\[[0-9.:-]+\]\s*/, '').trim();
      let speaker = 'ACTION';

      if (text.startsWith('CAMERA:')) {
        speaker = 'CAMERA';
        text = text.replace('CAMERA:', '').trim();
      } else if (text.startsWith('ACTION:')) {
        speaker = 'ACTION';
        text = text.replace('ACTION:', '').trim();
      } else if (text.startsWith('SOUND FX:') || text.startsWith('SOUND:')) {
        speaker = 'SOUND FX';
        text = text.replace(/SOUND( FX)?:/, '').trim();
      } else {
        const colon = text.indexOf(':');
        if (colon > 0 && colon < 30) {
          speaker = text.substring(0, colon).trim();
          text = text.substring(colon + 1).trim();
        }
      }

      return {
        id: idx,
        speaker,
        text,
        absStart: timeMatch ? parseFloat(timeMatch[1]) : current.clipStart + idx * 2,
        absEnd: timeMatch ? parseFloat(timeMatch[2]) : current.clipStart + (idx + 1) * 2,
      };
    });
  }, [current]);

  const duration = current?.duration || 45;

  // Playing stops by itself at the end of the clip (derived, no extra state to keep in sync).
  const playing = isPlaying && currentTime < duration;

  // Timer loop for simulation
  useEffect(() => {
    if (playing) {
      intervalRef.current = setInterval(() => {
        setCurrentTime((prev) => Math.min(duration, prev + 0.1 * playbackSpeed));
      }, 100);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [playing, duration, playbackSpeed]);

  // Sound cues (kept out of the timer so they fire once, even under StrictMode).
  useEffect(() => {
    if (!playing || !audioEnabled) return;
    if (currentTime >= 0.2 && !hitTriggeredRef.current) {
      playCinematicHit();
      hitTriggeredRef.current = true;
    }
    if (currentTime >= duration - CLIFFHANGER_WINDOW_SECONDS && !cliffTriggeredRef.current) {
      playCliffhangerTension();
      cliffTriggeredRef.current = true;
    }
  }, [currentTime, playing, audioEnabled, duration]);

  const togglePlay = () => {
    if (playing) {
      setIsPlaying(false);
      return;
    }
    // Pressing play on a finished clip replays it from the start.
    if (currentTime >= duration) {
      setCurrentTime(0);
      hitTriggeredRef.current = false;
      cliffTriggeredRef.current = false;
    }
    setIsPlaying(true);
  };

  const handleReset = () => {
    setIsPlaying(false);
    setCurrentTime(0);
    hitTriggeredRef.current = false;
    cliffTriggeredRef.current = false;
  };

  const isHookWindow = currentTime <= HOOK_WINDOW_SECONDS;
  const isCliffhangerWindow = currentTime >= Math.max(0, duration - CLIFFHANGER_WINDOW_SECONDS);

  // Teleprompter: follow the real line timestamps (relative to the clip start).
  let activeIdx = 0;
  lines.forEach((l, i) => {
    if (l.absStart - (current?.clipStart || 0) <= currentTime) activeIdx = i;
  });
  const visibleStart = Math.max(0, Math.min(activeIdx - 1, lines.length - 5));

  if (!current) {
    return (
      <EmptyState icon={Play} title="No clip to preview">
        There are no promos in this view yet.
      </EmptyState>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Top selector */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white border border-slate-200/90 p-4 rounded-2xl shadow-xs">
        <div>
          <span className="text-xs text-slate-500 font-medium">Previewing Vertical Promo:</span>
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <span className="text-rose-600 font-extrabold">Rank #{current?.rank}</span> · {current?.episode} ({current?.clipStart}s–{current?.clipEnd}s)
          </h2>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={current?.id}
            onChange={(e) => {
              const found = candidates.find((c) => c.id === e.target.value);
              if (found) {
                onSelectCandidate(found);
              }
            }}
            className="px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 font-medium focus:bg-white focus:outline-none focus:border-rose-500"
          >
            {candidates.slice(0, 25).map((c) => (
              <option key={c.id} value={c.id}>
                #{c.rank} · {c.episode} ({c.duration}s, Score: {c.hybridScore})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Simulator Layout: Phone in center, analysis on right */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-8 items-center justify-center">
        {/* Phone Mockup Frame (5 cols) */}
        <div className="md:col-span-5 flex justify-center">
          <div className="relative w-[310px] h-[610px] bg-slate-950 rounded-[44px] border-4 border-slate-300 shadow-2xl overflow-hidden flex flex-col justify-between p-4">
            {/* Phone Notch */}
            <div className="absolute top-2 left-1/2 -translate-x-1/2 w-28 h-4 bg-slate-800 rounded-full z-30" />

            {/* In-Video Status Overlays */}
            <div className="relative z-20 pt-6 space-y-2">
              <div className="flex items-center justify-between text-[10px] text-white/80">
                <span className="font-semibold">{current?.episode}</span>
                <span className="font-mono bg-black/60 px-1.5 py-0.5 rounded text-white">
                  {currentTime.toFixed(1)}s / {duration.toFixed(1)}s
                </span>
              </div>

              {/* Hook / Cliffhanger Alert Banner */}
              {isHookWindow && (
                <div className="bg-emerald-500 text-slate-950 font-extrabold text-[10px] px-2.5 py-1 rounded-lg text-center shadow-lg animate-pulse">
                  ⚡ 0–{HOOK_WINDOW_SECONDS}s INSTANT HOOK WINDOW
                </div>
              )}
              {isCliffhangerWindow && (
                <div className="bg-rose-600 text-white font-extrabold text-[10px] px-2.5 py-1 rounded-lg text-center shadow-lg animate-pulse">
                  🛑 CLIFFHANGER CUTOFF (NO SPOILER)
                </div>
              )}
            </div>

            {/* Vertical Video Teleprompter Content */}
            <div className="relative z-10 flex-1 my-3 overflow-y-auto space-y-3 px-1 no-scrollbar text-center flex flex-col justify-center">
              {lines.slice(visibleStart, visibleStart + 5).map((line) => {
                const idx = line.id;
                const isCurrent = idx === activeIdx;

                let badgeColor = 'bg-slate-800 text-slate-300';
                if (line.speaker === 'CAMERA') badgeColor = 'bg-indigo-900/60 text-indigo-300';
                if (line.speaker === 'ACTION') badgeColor = 'bg-amber-900/60 text-amber-300';
                if (line.speaker === 'SOUND FX') badgeColor = 'bg-purple-900/60 text-purple-300';

                return (
                  <div
                    key={idx}
                    className={`transition-all duration-300 p-2.5 rounded-xl ${
                      isCurrent
                        ? 'bg-rose-950/50 border border-rose-500/50 scale-105 shadow-md'
                        : 'opacity-40'
                    }`}
                  >
                    <div className="mb-0.5">
                      <span className={`text-[9px] font-bold px-1.5 py-0.2 rounded ${badgeColor}`}>
                        {line.speaker}
                      </span>
                    </div>
                    <p className="text-[11px] font-medium text-white leading-snug">
                      {line.text}
                    </p>
                  </div>
                );
              })}
            </div>

            {/* Phone Bottom Controls & Scrubber */}
            <div className="relative z-20 space-y-2 pt-2 border-t border-slate-800/80">
              <input
                type="range"
                min="0"
                max={duration}
                step="0.1"
                value={currentTime}
                onChange={(e) => setCurrentTime(parseFloat(e.target.value))}
                className="w-full accent-rose-500 h-1 bg-slate-800 rounded-lg cursor-pointer"
              />

              <div className="flex items-center justify-between text-xs text-white">
                <button
                  onClick={togglePlay}
                  className="w-8 h-8 rounded-full bg-rose-600 hover:bg-rose-500 flex items-center justify-center shadow"
                >
                  {playing ? <Pause className="w-4 h-4 fill-current" /> : <Play className="w-4 h-4 fill-current ml-0.5" />}
                </button>

                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setAudioEnabled(!audioEnabled)}
                    title={audioEnabled ? 'Mute SFX' : 'Enable Dramatic SFX'}
                    className={`p-1.5 rounded-lg transition-colors ${
                      audioEnabled ? 'text-rose-400 bg-rose-500/10' : 'text-slate-500 hover:text-white'
                    }`}
                  >
                    {audioEnabled ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
                  </button>
                  <button
                    onClick={handleReset}
                    className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => setPlaybackSpeed(playbackSpeed === 1 ? 1.5 : playbackSpeed === 1.5 ? 2 : 1)}
                    className="px-1.5 py-0.5 bg-slate-800 hover:bg-slate-700 text-[10px] font-mono rounded text-slate-300"
                  >
                    {playbackSpeed}x
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Narrative & Pacing Inspector (7 cols) */}
        <div className="md:col-span-7 space-y-5 bg-white border border-slate-200/90 p-6 rounded-2xl shadow-xs">
          <div>
            <span className="text-xs font-bold text-rose-600 uppercase tracking-wider">Vertical Promo Playback</span>
            <h3 className="text-lg font-bold text-slate-900 mt-1">Why this window works in 9:16 Short-Form</h3>
            <p className="text-xs text-slate-600 mt-1 leading-relaxed">
              {current?.whyItWorks || 'Combines high-tension verbal or physical confrontation with instant hook retention.'}
            </p>
          </div>

          <div className="space-y-3">
            <div className="p-4 bg-emerald-50/60 rounded-xl border border-emerald-200">
              <div className="text-xs font-bold text-emerald-800 mb-1 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-emerald-600" /> Hook Execution (0.0s – 3.0s)
              </div>
              <p className="text-xs text-slate-700 italic">
                "{unquote(current?.hook) || 'Instant dramatic dialogue line'}"
              </p>
              <div className="text-[11px] text-slate-500 mt-1.5">
                Hook Score: <strong className="text-slate-800">{current?.hookScore}/10</strong> · Verified at t = {current?.hookTimestamp ?? 0}s
              </div>
            </div>

            <div className="p-4 bg-rose-50/60 rounded-xl border border-rose-200">
              <div className="text-xs font-bold text-rose-800 mb-1 flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5 text-rose-600" /> Cliffhanger Drop (Final 5 seconds)
              </div>
              <p className="text-xs text-slate-700 italic">
                "{unquote(current?.cliffhanger) || 'Cut right before secret reveal'}"
              </p>
              <div className="text-[11px] text-slate-500 mt-1.5">
                Cliffhanger Score: <strong className="text-slate-800">{current?.cliffhangerScore}/10</strong> · Cuts at t = {current?.clipEnd}s
              </div>
            </div>
          </div>

          <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-1.5">
            <div className="text-slate-800 font-semibold flex items-center justify-between">
              <span>Video Editor Sound & Mix Notes:</span>
              <span className="text-[10px] text-emerald-700 font-bold bg-emerald-100 px-2 py-0.5 rounded-full">SFX Active</span>
            </div>
            <p className="text-slate-600 text-[11px] leading-relaxed">
              • An opening impact sub-bass hit is automatically simulated on mobile feed entry (at t = 0 s) to stop viewers from scrolling past.<br />
              • A tension riser frequency is simulated in the final {CLIFFHANGER_WINDOW_SECONDS}s window (t ≥ T − {CLIFFHANGER_WINDOW_SECONDS} s) right before the cliffhanger cut.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
