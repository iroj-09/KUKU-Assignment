// Small text helpers shared by the pages.

/** Hooks and cliffhangers often arrive already wrapped in quote marks; the layout adds its own, so strip those. */
export function unquote(text) {
  return String(text ?? '')
    .trim()
    .replace(/^["\u201c\u201d]+/, '')
    .replace(/["\u201c\u201d]+$/, '')
    .trim();
}
