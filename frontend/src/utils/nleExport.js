// Client-side NLE Video Editor Exporters

export function framesToTimecode(totalFrames, fps = 24) {
  totalFrames = Math.max(0, Math.round(totalFrames));
  const ff = totalFrames % fps;
  const totalSec = Math.floor(totalFrames / fps);
  const ss = totalSec % 60;
  const mm = Math.floor(totalSec / 60) % 60;
  const hh = Math.floor(totalSec / 3600);

  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(hh)}:${pad(mm)}:${pad(ss)}:${pad(ff)}`;
}

export function secondsToFrames(seconds, fps = 24) {
  return Math.round(Math.max(0, Number(seconds) || 0) * fps);
}

export function secondsToTimecode(seconds, fps = 24) {
  return framesToTimecode(secondsToFrames(seconds, fps), fps);
}

// Quote every field and neutralise spreadsheet formulas (=, +, -, @).
function csvField(v) {
  let s = v == null ? '' : String(v);
  if (/^[=+\-@\t\r]/.test(s) && Number.isNaN(Number(s))) s = `'${s}`;
  return `"${s.replace(/"/g, '""')}"`;
}

const oneLine = (v) => String(v ?? '').replace(/[\r\n]+/g, ' ').trim();

// Duration from the rounded in/out frames so In + Duration == Out exactly.
function durationTimecode(c, fps) {
  return framesToTimecode(secondsToFrames(c.clipEnd, fps) - secondsToFrames(c.clipStart, fps), fps);
}

export function generateDaVinciMarkers(candidates, fps = 24) {
  const rows = [['Name', 'Description', 'In', 'Out', 'Duration', 'Color']];

  candidates.forEach((c) => {
    const rank = c.rank ?? '';
    const name = rank ? `Rank${rank}_${c.episode}` : `Promo_${c.episode}`;
    const desc = `Score: ${c.hybridScore} | ${c.whyItWorks || c.hook || ''}`;
    const tcIn = secondsToTimecode(c.clipStart, fps);
    const tcOut = secondsToTimecode(c.clipEnd, fps);
    const tcDur = durationTimecode(c, fps);
    const color = (c.hybridScore || 0) >= 75 ? 'Cyan' : 'Green';

    rows.push([name, desc, tcIn, tcOut, tcDur, color]);
  });

  return rows.map((r) => r.map(csvField).join(',')).join('\n');
}

export function generatePremiereMarkers(candidates, fps = 24) {
  const rows = [['Marker Name', 'Description', 'In', 'Out', 'Duration', 'Marker Type']];

  candidates.forEach((c) => {
    const rank = c.rank ?? '';
    const name = rank ? `Rank${rank}_${c.episode}` : `Promo_${c.episode}`;
    const desc = `Score: ${c.hybridScore} | ${c.whyItWorks || c.hook || ''}`;
    const tcIn = secondsToTimecode(c.clipStart, fps);
    const tcOut = secondsToTimecode(c.clipEnd, fps);
    const tcDur = durationTimecode(c, fps);

    rows.push([name, desc, tcIn, tcOut, tcDur, 'Comment']);
  });

  return rows.map((r) => r.map(csvField).join(',')).join('\n');
}

export function generateCmxEdl(candidates, title = 'KUKU_PROMOS', fps = 24) {
  const lines = [
    `TITLE: ${oneLine(title)}`,
    'FCM: NON-DROP FRAME',
    '',
  ];

  // Work in whole frames so source and record durations always match (EDL requirement).
  let recordFrames = 0;

  candidates.forEach((c, idx) => {
    const eventNum = String(idx + 1).padStart(3, '0');
    const srcInF = secondsToFrames(c.clipStart, fps);
    const srcOutF = secondsToFrames(c.clipEnd, fps);
    const srcIn = framesToTimecode(srcInF, fps);
    const srcOut = framesToTimecode(srcOutF, fps);
    const recIn = framesToTimecode(recordFrames, fps);
    recordFrames += srcOutF - srcInF;
    const recOut = framesToTimecode(recordFrames, fps);

    lines.push(`${eventNum}  AX       V     C        ${srcIn} ${srcOut} ${recIn} ${recOut}`);
    lines.push(`* FROM CLIP NAME: ${oneLine(c.episode)}`);
    if (c.whyItWorks) {
      lines.push(`* COMMENT: Rank ${c.rank || idx + 1} - ${oneLine(c.whyItWorks)}`);
    }
    lines.push('');
  });

  return lines.join('\n');
}

export function downloadFile(content, fileName, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
