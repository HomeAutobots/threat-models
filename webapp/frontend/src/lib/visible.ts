const NON_PRINTABLE = /^[\p{C}\p{Z}]$/u

/**
 * Mirrors tmreg's cli.visible: every character except newline, tab, and a plain space that is in
 * a Unicode category C* or Z* is shown as an escape, so stored text cannot hide itself.
 */
export function visible(text: string): string {
  let out = ''
  for (const ch of text) {
    if (ch === '\n' || ch === '\t' || ch === ' ' || !NON_PRINTABLE.test(ch)) {
      out += ch
      continue
    }
    if (ch === '\r') {
      out += '\\r' // Python's unicode_escape writes CR as \r, not \x0d
      continue
    }
    const n = ch.codePointAt(0) as number
    if (n <= 0xff) out += '\\x' + n.toString(16).padStart(2, '0')
    else if (n <= 0xffff) out += '\\u' + n.toString(16).padStart(4, '0')
    else out += '\\U' + n.toString(16).padStart(8, '0')
  }
  return out
}
