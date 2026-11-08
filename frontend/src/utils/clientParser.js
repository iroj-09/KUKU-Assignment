// Client-side parser and beat-aligned promo window generator

const HOOK_TERMS = [
  'what', 'why', 'no', 'stop', 'how dare', 'you lied', 'betray', 'marry',
  'kill', 'secret', 'caught', 'never', 'listen', 'who', 'wait', 'duke', 'bastard', 'liar'
];

const CLIFF_TERMS = [
  'but', 'unless', 'who are you', 'what happened', 'you will', 'not yet',
  'the truth', 'secret', 'door', 'footsteps', 'wait', 'tomorrow', 'or else',
  'kill', 'die', 'blood', 'brand', 'promise', 'never', 'silence', 'touch'
];

const EMOTION_TERMS = [
  'cry', 'tears', 'shock', 'shocked', 'furious', 'scream', 'screaming',
  'betray', 'heartbroken', 'desperate', 'gasp', 'slap', 'blood', 'gun',
  'threat', 'revenge', 'rage', 'hatred', 'love', 'pain', 'murder'
];

function hits(text, terms) {
  const t = (text || '').toLowerCase();
  return terms.reduce((acc, term) => acc + (t.includes(term) ? 1 : 0), 0);
}

// Keep in sync with HOOK_WINDOW_SECONDS / CLIFFHANGER_WINDOW_SECONDS in the root config.py.
export const HOOK_WINDOW_SECONDS = 3;
export const CLIFFHANGER_WINDOW_SECONDS = 5;

export function parseTimeToSeconds(val) {
  if (typeof val === 'number') return val;
  const clean = String(val).trim().replace(',', '.');
  const parts = clean.split(':');
  if (parts.length === 2) {
    const mm = parseInt(parts[0], 10) || 0;
    const ss = parseFloat(parts[1]) || 0;
    return mm * 60 + ss;
  } else if (parts.length === 3) {
    const hh = parseInt(parts[0], 10) || 0;
    const mm = parseInt(parts[1], 10) || 0;
    const ss = parseFloat(parts[2]) || 0;
    return hh * 3600 + mm * 60 + ss;
  }
  return parseFloat(clean) || 0;
}

export function parseSrt(text, filename) {
  const blocks = text.trim().split(/\n\s*\n/);
  const events = [];

  blocks.forEach((block) => {
    const lines = block.split('\n').map((l) => l.trim()).filter(Boolean);
    const timeIdx = lines.findIndex((l) => l.includes('-->'));
    if (timeIdx === -1) return;

    const parts = lines[timeIdx].split('-->');
    const start = parseTimeToSeconds(parts[0]);
    const end = parseTimeToSeconds(parts[1]);
    let subText = lines.slice(timeIdx + 1).join(' ').replace(/<[^>]+>/g, '').trim();

    let speaker = 'DIALOGUE';
    const colonMatch = subText.match(/^([A-Z\s]{2,20}):\s*(.+)$/);
    if (colonMatch) {
      speaker = colonMatch[1].trim();
      subText = colonMatch[2].trim();
    }

    if (subText && end > start) {
      events.push({
        type: speaker,
        start: Number(start.toFixed(2)),
        end: Number(end.toFixed(2)),
        duration: Number((end - start).toFixed(2)),
        text: subText,
      });
    }
  });

  return {
    episode: filename.replace(/\.[^/.]+$/, ''),
    events,
  };
}

export function parseKukuText(text, filename) {
  const epMatch = text.match(/^EPISODE NUMBER:\s*(.+)$/m);
  const lines = text.split('\n');
  const events = [];

  let currentLabel = 'GENERAL';
  let i = 0;

  const eventRe = /^Start:\s*\(([0-9:.]+)\)\s*\|\s*End:\s*\(([0-9:.]+)\)/;

  while (i < lines.length) {
    const line = lines[i].trim();

    if (line.startsWith('**') && line.endsWith(':**')) {
      currentLabel = line.replace(/\*/g, '').replace(':', '').trim();
    } else if (line.endsWith(':') && !line.startsWith('Start:') && line.length < 100) {
      currentLabel = line.slice(0, -1).trim();
    }

    const em = line.match(eventRe);
    if (em) {
      const start = parseTimeToSeconds(em[1]);
      const end = parseTimeToSeconds(em[2]);
      const body = [];
      let j = i + 1;
      while (j < lines.length) {
        const nxt = lines[j].trim();
        if (nxt.match(eventRe) || nxt.match(/^SCENE\s+\d+/i) || nxt.startsWith('--- SCRIPT')) break;
        if (nxt.startsWith('**') && nxt.endsWith(':**')) break;
        if (nxt && nxt !== 'Actions and dialogue:') body.push(nxt);
        j++;
      }
      const content = body.join(' ').trim();
      if (content && end > start) {
        events.push({
          type: currentLabel,
          start: Number(start.toFixed(2)),
          end: Number(end.toFixed(2)),
          duration: Number((end - start).toFixed(2)),
          text: content,
        });
      }
      i = j;
      continue;
    }
    i++;
  }

  // Fallback: if no Start: () | End: () lines found, check for timestamps in brackets [00:01.00 - 00:05.00]
  if (events.length === 0) {
    const bracketRe = /\[([0-9:.]+)\s*-\s*([0-9:.]+)\]\s*([^[]+)/g;
    let match;
    while ((match = bracketRe.exec(text)) !== null) {
      const start = parseTimeToSeconds(match[1]);
      const end = parseTimeToSeconds(match[2]);
      const body = match[3].trim();
      if (body && end > start) {
        events.push({
          type: 'DIALOGUE',
          start: Number(start.toFixed(2)),
          end: Number(end.toFixed(2)),
          duration: Number((end - start).toFixed(2)),
          text: body,
        });
      }
    }
  }

  return {
    episode: epMatch ? epMatch[1].trim() : filename.replace(/\.[^/.]+$/, ''),
    events,
  };
}

export function parseFountain(text, filename) {
  const lines = text.split('\n');
  const events = [];
  let currentTime = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (/^[A-Z0-9\s_'-]{2,25}$/.test(line) && i + 1 < lines.length) {
      const speaker = line;
      const dial = [];
      let j = i + 1;
      while (j < lines.length && lines[j].trim()) {
        dial.push(lines[j].trim());
        j++;
      }
      const dialText = dial.join(' ');
      const words = dialText.split(/\s+/).length;
      const dur = Math.max(1.8, Math.round((words / 2.5) * 10) / 10);
      const start = currentTime;
      const end = Number((start + dur).toFixed(2));
      currentTime = end + 0.5;

      events.push({
        type: speaker,
        start,
        end,
        duration: dur,
        text: `${speaker}: "${dialText}"`,
      });
      i = j;
    }
  }

  return {
    episode: filename.replace(/\.[^/.]+$/, ''),
    events,
  };
}

export function parseFile(text, filename) {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.srt') || text.includes('-->')) {
    return parseSrt(text, filename);
  }
  if (lower.endsWith('.fountain')) {
    return parseFountain(text, filename);
  }
  return parseKukuText(text, filename);
}

export function generateCandidatesFromScript(parsed, minDuration = 20, maxDuration = 60, maxPerScript = 12) {
  const NON_SPOKEN_TYPES = ['CAMERA', 'ACTION', 'SOUND FX', 'SOUND'];
  const { episode, events } = parsed;
  if (!events || events.length === 0) return [];

  const candidates = [];
  const seen = new Set();

  for (let i = 0; i < events.length; i++) {
    const startEv = events[i];
    const clipStart = startEv.start;

    for (let j = i; j < events.length; j++) {
      const endEv = events[j];
      const clipEnd = endEv.end;
      const duration = clipEnd - clipStart;

      if (duration < minDuration - 0.01) continue;
      if (duration > maxDuration + 0.01) break;

      const key = `${clipStart.toFixed(1)}_${clipEnd.toFixed(1)}`;
      if (seen.has(key)) continue;

      const selected = events.filter((e) => e.end > clipStart + 0.01 && e.start < clipEnd - 0.01);
      if (selected.length === 0) continue;

      seen.add(key);

      // Same '[start-end] TYPE: text' layout as the Python pipeline's full_transcript, so the
      // simulator can time lines and Gemini sees real timestamps to anchor hook/cliffhanger on.
      const transcript = selected
        .map((e) => `[${e.start.toFixed(2)}-${e.end.toFixed(2)}] ${e.type}: ${e.text}`)
        .join('\n')
        .trim();
      const plainText = selected.map((e) => e.text).join(' ');
      const wordCount = plainText.split(/\s+/).filter(Boolean).length;
      // WPM counts spoken dialogue only (camera/action/sound lines are not spoken).
      const spokenWords = selected
        .filter((e) => !NON_SPOKEN_TYPES.includes(String(e.type || '').toUpperCase()))
        .reduce((n, e) => n + e.text.split(/\s+/).filter(Boolean).length, 0);
      const wpm = Number(((spokenWords / Math.max(1, duration)) * 60).toFixed(1));

      // Hook and Cliffhanger
      const hookEvents = selected.filter((e) => e.start <= clipStart + HOOK_WINDOW_SECONDS);
      const cliffEvents = selected.filter((e) => e.end >= clipEnd - CLIFFHANGER_WINDOW_SECONDS);

      const hookText = (hookEvents.length > 0 ? hookEvents : selected.slice(0, 1)).map((e) => e.text).join(' ');
      const cliffText = (cliffEvents.length > 0 ? cliffEvents : selected.slice(-1)).map((e) => e.text).join(' ');

      const hookScore = Math.min(10, hits(hookText, HOOK_TERMS) * 2.2 + 2.0);
      const cliffScore = Math.min(10, hits(cliffText, CLIFF_TERMS) * 2.0 + 1.5);
      const emoScore = Math.min(10, hits(plainText, EMOTION_TERMS) * 1.5);
      const dialogueScore = Math.min(10, selected.filter((e) => !NON_SPOKEN_TYPES.includes(String(e.type || '').toUpperCase())).length * 0.8);
      const standaloneScore = wordCount >= 25 && wpm >= 80 && wpm <= 200 ? 5.0 : 3.0;

      const totalHeuristic = Number(((0.30 * hookScore + 0.30 * cliffScore + 0.20 * emoScore + 0.10 * dialogueScore + 0.10 * standaloneScore) * 10).toFixed(1));

      candidates.push({
        id: `${episode}|${clipStart.toFixed(1)}|${clipEnd.toFixed(1)}`,
        episode,
        episodeFile: episode,
        clipStart: Number(clipStart.toFixed(1)),
        clipEnd: Number(clipEnd.toFixed(1)),
        duration: Number(duration.toFixed(1)),
        hybridScore: totalHeuristic,
        geminiScore: totalHeuristic,
        localScore: totalHeuristic,
        // Not checked against Gemini evidence yet (mirrors the Python pipeline's UNVERIFIED).
        compliance: 'UNVERIFIED',
        isPromising: totalHeuristic >= 60,
        hook: hookText.slice(0, 140),
        hookTimestamp: clipStart,
        cliffhanger: cliffText.slice(0, 140),
        cliffhangerTimestamp: clipEnd,
        whyItWorks: 'Beat-aligned high tension window discovered in browser.',
        standaloneContext: 'Self-contained scene conflict.',
        risks: [],
        hookScore: Number(hookScore.toFixed(1)),
        cliffhangerScore: Number(cliffScore.toFixed(1)),
        emotionalScore: Number(emoScore.toFixed(1)),
        standaloneScore: Number(standaloneScore.toFixed(1)),
        progressionScore: 7.0,
        fullTranscript: transcript,
        wpm,
        wordCount,
        reviewStatus: 'Pending human review',
      });
    }
  }

  // Deduplicate overlapping candidates: overlap / shorter clip >= 0.50 (same rule as src/deduplicate.py)
  candidates.sort((a, b) => b.hybridScore - a.hybridScore);

  const retained = [];
  for (const cand of candidates) {
    const hasHeavyOverlap = retained.some((r) => {
      const inter = Math.max(0, Math.min(cand.clipEnd, r.clipEnd) - Math.max(cand.clipStart, r.clipStart));
      const shorter = Math.min(cand.duration, r.duration);
      return shorter > 0 && inter / shorter >= 0.5;
    });

    if (!hasHeavyOverlap) {
      retained.push(cand);
      if (retained.length >= maxPerScript) break;
    }
  }

  return retained;
}
