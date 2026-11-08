// The clips generated from the user's uploaded scripts are kept in this browser (IndexedDB) so a
// page refresh does not lose them. They never leave the computer. Every call fails soft: if
// storage is blocked (private window, no space) the app simply behaves as before.
const DB = 'kuku_promo_studio';
const STORE = 'kv';
const KEY = 'upload';

function open() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('IndexedDB unavailable'));
      return;
    }
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function run(mode, fn) {
  const db = await open();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      const req = fn(tx.objectStore(STORE));
      tx.oncomplete = () => resolve(req.result);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}

/** @returns {Promise<{sources: string[], candidates: object[]} | null>} */
export async function loadUpload() {
  try {
    const saved = await run('readonly', (s) => s.get(KEY));
    if (saved && Array.isArray(saved.sources) && Array.isArray(saved.candidates) && saved.candidates.length) return saved;
  } catch (e) {
    console.warn('Could not read saved uploads', e);
  }
  return null;
}

export async function saveUpload(sources, candidates) {
  try {
    await run('readwrite', (s) => s.put({ sources, candidates }, KEY));
  } catch (e) {
    console.warn('Could not save uploads', e);
  }
}

export async function clearUpload() {
  try {
    await run('readwrite', (s) => s.delete(KEY));
  } catch (e) {
    console.warn('Could not clear saved uploads', e);
  }
}
