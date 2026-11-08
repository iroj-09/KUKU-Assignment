// Saved pipeline results for screenplay files this project has already analysed.
//
// scripts/build_known_results.py fingerprints each input file (SHA-256 of its bytes) and stores the promos the
// Python pipeline found in it. Uploading the same file again shows those promos, so the app agrees with the
// submitted raw outputs. Any other file is processed in the browser. The data file holds screenplay text, so it is
// git-ignored; an app built from a clean clone has none and always processes in the browser.
const loaders = import.meta.glob('../data/known_results.json');
let cache = null;

async function loadKnown() {
  if (cache) return cache;
  const load = loaders['../data/known_results.json'];
  try {
    cache = load ? (await load()).default || {} : {};
  } catch (e) {
    console.warn('Could not load saved results', e);
    cache = {};
  }
  return cache;
}

async function sha256Hex(buffer) {
  const digest = await crypto.subtle.digest('SHA-256', buffer);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * @param {File} file
 * @returns {Promise<object[] | null>} the saved promos for this exact file, or null if it is not a known file
 */
export async function savedResultsFor(file) {
  const known = await loadKnown();
  if (!Object.keys(known).length || !globalThis.crypto?.subtle) return null;
  try {
    const hit = known[await sha256Hex(await file.arrayBuffer())];
    return hit ? hit.candidates : null;
  } catch (e) {
    console.warn('Could not fingerprint the file', e);
    return null;
  }
}
