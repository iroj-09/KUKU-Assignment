import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  generateCmxEdl,
  generateDaVinciMarkers,
  secondsToTimecode,
  framesToTimecode,
} from './nleExport';
import {
  parseFile,
  generateCandidatesFromScript,
  HOOK_WINDOW_SECONDS,
  CLIFFHANGER_WINDOW_SECONDS,
} from './clientParser';
import { evaluateBatchWithGemini, evaluateCandidateWithGemini } from './geminiEvaluator';
import { unquote } from './text';

const tcToFrames = (tc, fps) => {
  const [h, m, s, f] = tc.split(':').map(Number);
  return ((h * 60 + m) * 60 + s) * fps + f;
};

describe('nleExport', () => {
  it('formats timecodes and clamps negatives', () => {
    expect(secondsToTimecode(61.5, 24)).toBe('00:01:01:12');
    expect(framesToTimecode(-5, 24)).toBe('00:00:00:00');
  });

  it('EDL source and record durations always match, at any fps', () => {
    const cands = [
      { clipStart: 10.3, clipEnd: 40.7, duration: 30.4, episode: 'E1', whyItWorks: 'a\nb', rank: 1 },
      { clipStart: 5.55, clipEnd: 51.15, duration: 45.6, episode: 'E2' },
      { clipStart: 0.1, clipEnd: 20.3, duration: 20.2, episode: 'E3' },
    ];
    for (const fps of [24, 30, 60]) {
      const edl = generateCmxEdl(cands, 'T', fps);
      const events = edl.split('\n').filter((l) => /^\d{3}\s+AX/.test(l));
      expect(events).toHaveLength(3);
      let prevRecOut = 0;
      for (const l of events) {
        const [srcIn, srcOut, recIn, recOut] = l.trim().split(/\s+/).slice(-4);
        expect(tcToFrames(srcOut, fps) - tcToFrames(srcIn, fps)).toBe(
          tcToFrames(recOut, fps) - tcToFrames(recIn, fps)
        );
        expect(tcToFrames(recIn, fps)).toBe(prevRecOut);
        prevRecOut = tcToFrames(recOut, fps);
      }
      expect(edl).not.toContain('a\nb'); // multi-line reasons are flattened
    }
  });

  it('marker CSV quotes every field', () => {
    const csv = generateDaVinciMarkers(
      [{ clipStart: 0, clipEnd: 30, duration: 30, episode: 'E "1"', hybridScore: 80, rank: 1 }],
      24
    );
    expect(csv.split('\n')[1]).toContain('"Rank1_E ""1"""');
  });
});

describe('clientParser', () => {
  // The ACTION line sits in the middle so every 20s+ window contains it.
  const script = [
    'EPISODE NUMBER: Episode 9',
    'SCENE 01',
    '**ALEXANDER:**',
    'Start: (00:00.00) | End: (00:12.00)',
    'Who sent you here tonight, tell me the truth',
    '**ACTION:**',
    'Start: (00:12.00) | End: (00:24.00)',
    'Wide shot of the hall with many guests standing around quietly',
    '**JULIANA:**',
    'Start: (00:24.00) | End: (00:36.00)',
    'I will never tell you the secret',
  ].join('\n');

  it('windows match the Python config (3s hook, 5s cliffhanger)', () => {
    expect(HOOK_WINDOW_SECONDS).toBe(3);
    expect(CLIFFHANGER_WINDOW_SECONDS).toBe(5);
  });

  it('builds timestamped transcripts, UNVERIFIED compliance, dialogue-only WPM', () => {
    const cands = generateCandidatesFromScript(parseFile(script, 'ep9.txt'), 20, 60, 5);
    expect(cands.length).toBeGreaterThan(0);
    for (const c of cands) {
      expect(c.compliance).toBe('UNVERIFIED');
      expect(c.fullTranscript).toMatch(/^\[\d+\.\d{2}-\d+\.\d{2}\] .+: .+/);
      expect(c.fullTranscript.split('\n').length).toBeGreaterThan(1);
    }
    // The 11-word action line must not count towards spoken WPM.
    const withAction = cands.filter((c) => c.fullTranscript.includes('Wide shot'));
    expect(withAction.length).toBeGreaterThan(0);
    for (const c of withAction) {
      expect(c.wpm).toBeCloseTo(((c.wordCount - 11) / c.duration) * 60, 0);
    }
  });
});

describe('geminiEvaluator', () => {
  afterEach(() => vi.unstubAllGlobals());

  const mk = (i) => ({
    id: `c${i}`, episode: `E${i}`, clipStart: 0, clipEnd: 30, duration: 30,
    fullTranscript: 'x', localScore: 50, hybridScore: 50,
  });
  const ok = {
    ok: true,
    json: async () => ({
      candidates: [{ content: { parts: [{ text: JSON.stringify({
        hook_score: 8, cliffhanger_score: 8, emotional_score: 8, standalone_score: 8,
        progression_score: 8, is_promising: true, hook_timestamp: 1, cliffhanger_timestamp: 28,
      }) }] } }],
    }),
  };
  const fail = (status) => ({
    ok: false, status, statusText: 'x',
    text: async () => JSON.stringify({ error: { message: 'API key not valid' } }),
  });

  // Skip the 1.2s rate-limit pause between calls.
  const fastTimers = () => vi.stubGlobal('setTimeout', (f) => { f(); return 0; });

  it('scores a clip and applies the strict 3s/5s compliance windows', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ok));
    const r = await evaluateCandidateWithGemini(mk(1), 'key', 'model');
    expect(r.geminiScore).toBe(80);
    expect(r.compliance).toBe('PASS');
  });

  it('stops after the first call on a bad key', async () => {
    fastTimers();
    const f = vi.fn(async () => fail(400));
    vi.stubGlobal('fetch', f);
    const r = await evaluateBatchWithGemini([1, 2, 3, 4].map(mk), 'k', 'm');
    expect(f).toHaveBeenCalledTimes(1);
    expect(r.abortReason).toBeTruthy();
    expect(r.candidates).toHaveLength(4);
  });

  it('continues past a transient error and counts it', async () => {
    fastTimers();
    let n = 0;
    vi.stubGlobal('fetch', vi.fn(async () => (++n === 2 ? fail(500) : ok)));
    const r = await evaluateBatchWithGemini([1, 2, 3, 4].map(mk), 'k', 'm');
    expect(r.failed).toBe(1);
    expect(r.evaluatedCount).toBe(3);
    expect(r.abortReason).toBeNull();
  });

  it('honours cancellation and keeps the rest unchanged', async () => {
    fastTimers();
    const ac = new AbortController();
    let n = 0;
    vi.stubGlobal('fetch', vi.fn(async () => { if (++n === 2) ac.abort(); return ok; }));
    const r = await evaluateBatchWithGemini([1, 2, 3, 4].map(mk), 'k', 'm', null, ac.signal);
    expect(r.cancelled).toBe(true);
    expect(r.evaluatedCount).toBe(2);
    expect(r.candidates).toHaveLength(4);
  });
});

describe('unquote', () => {
  it('strips quote marks the data already carries, so the layout can add its own once', () => {
    expect(unquote('"I will return."')).toBe('I will return.');
    expect(unquote('\u201cWait\u2026\u201d')).toBe('Wait\u2026');
    expect(unquote('""double""')).toBe('double');
    expect(unquote("it's fine")).toBe("it's fine"); // apostrophes inside words are kept
    expect(unquote(null)).toBe('');
    expect(unquote(undefined)).toBe('');
  });
});
