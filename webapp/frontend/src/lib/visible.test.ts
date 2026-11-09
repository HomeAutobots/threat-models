import { describe, expect, it } from 'vitest'
import { visible } from './visible'

describe('visible', () => {
  it('escapes control characters', () => {
    expect(visible('a\x1bb')).toBe('a\\x1bb')
  })
  it('escapes bidi overrides', () => {
    expect(visible('x‮y')).toBe('x\\u202ey')
  })
  it('keeps newline, tab, and ordinary text', () => {
    expect(visible('line\nnext\ttab')).toBe('line\nnext\ttab')
    expect(visible('café 東京')).toBe('café 東京')
  })
  it('escapes a no-break space but not a plain one', () => {
    expect(visible(' ')).toBe('\\xa0')
    expect(visible('a b')).toBe('a b')
  })
  it('escapes astral non-printables with eight digits', () => {
    expect(visible('\u{e0001}')).toBe('\\U000e0001')
  })
})
