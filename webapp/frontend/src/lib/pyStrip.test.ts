import { describe, expect, it } from 'vitest'
import { noteLength, pyStrip } from './pyStrip'

describe('pyStrip', () => {
  it('strips what Python str.strip() strips, including U+001C and U+0085', () => {
    expect(pyStrip('\u001cabc\u0085')).toBe('abc')
    expect(pyStrip('\u001f\u001e\u001d x         　')).toBe('x')
    expect(pyStrip('\t\n\u000b\u000c\r a b \r\n')).toBe('a b')
  })
  it('does not strip U+FEFF, which JS trim() does but Python does not', () => {
    expect(pyStrip('﻿abc﻿')).toBe('﻿abc﻿')
    expect(pyStrip(' ﻿ ')).toBe('﻿')
    expect(' ﻿ '.trim()).toBe('')
  })
  it('does not strip U+200B or U+180E, which Python does not treat as space', () => {
    expect(pyStrip('​x​')).toBe('​x​')
    expect(pyStrip('᠎x')).toBe('᠎x')
  })
  it('strips only the outside', () => {
    expect(pyStrip('  a  b  ')).toBe('a  b')
    expect(pyStrip('   ')).toBe('')
  })
})

describe('noteLength', () => {
  it('counts code points of the stripped text', () => {
    expect(noteLength('\u001c\u0085 ab\u{1f600}  ')).toBe(3)
    expect(noteLength('﻿')).toBe(1)
    expect(noteLength('')).toBe(0)
  })
})
