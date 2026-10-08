// Text normalisation shared by "is this unsaved?" checks and validation.
// The same normalisation is applied to both sides of a comparison (plan 5.1):
// line endings are unified (CRLF/CR -> LF) and leading/trailing whitespace
// is removed, matching what the server stores (str.strip()).

export const ANALYSIS_TITLE_MAX = 255;

export function normalizeText(value) {
  return String(value ?? '').replace(/\r\n?/g, '\n').trim();
}

export function isSameText(a, b) {
  return normalizeText(a) === normalizeText(b);
}

// Counts characters the way the server does (Python len(): code points), so a
// title with characters outside the BMP (e.g. 𠮷) is not rejected early.
export function countChars(value) {
  return Array.from(String(value ?? '')).length;
}

export function validateAnalysisTitle(value) {
  const title = normalizeText(value);
  if (!title) return 'タイトルは必須です';
  if (countChars(title) > ANALYSIS_TITLE_MAX) {
    return `タイトルは${ANALYSIS_TITLE_MAX}文字以内で入力してください`;
  }
  return null;
}

export function truncateForDisplay(value, max = 40) {
  const chars = Array.from(normalizeText(value));
  return chars.length > max ? `${chars.slice(0, max).join('')}…` : chars.join('');
}
