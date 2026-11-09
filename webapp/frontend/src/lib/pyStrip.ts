// Python's str.isspace() set, which is what the core's str.strip() removes: U+0009 to U+000D,
// U+001C to U+001F, U+0020, U+0085, U+00A0, U+1680, U+2000 to U+200A, U+2028, U+2029, U+202F,
// U+205F, and U+3000. JS trim() differs: it also removes U+FEFF, and it keeps U+001C to U+001F
// and U+0085. The note counters must agree with the core, so they use this.
const PY_SPACE = '\\t-\\r\\u001c-\\u0020\\u0085\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000'
const OUTER = new RegExp(`^[${PY_SPACE}]+|[${PY_SPACE}]+$`, 'g')

export function pyStrip(s: string): string {
  return s.replace(OUTER, '')
}

/** The length the core checks a note against: code points of the text without outer whitespace. */
export function noteLength(s: string): number {
  return [...pyStrip(s)].length
}
