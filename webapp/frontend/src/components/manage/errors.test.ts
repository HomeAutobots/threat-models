import { describe, expect, it } from 'vitest'
import { ApiError } from '../../api/client'
import { failure, refusalText, TERMINAL_HINT } from './errors'

const HUMAN = 'merge is human-only and needs an interactive terminal. Run it yourself in a terminal.'
const NO_RUN = 'non-interactive writes must name a run: pass --run <run-id>'

describe('refusalText', () => {
  it('adds the hint after core\'s message for the two refusals', () => {
    expect(refusalText(HUMAN)).toBe(`${HUMAN}\n${TERMINAL_HINT}`)
    expect(refusalText(NO_RUN)).toBe(`${NO_RUN}\n${TERMINAL_HINT}`)
  })

  it('leaves every other message alone, and escapes it', () => {
    expect(refusalText('note too short')).toBe('note too short')
    expect(refusalText('bad‮gnp')).toBe('bad\\u202egnp')
  })

  it('failure() uses it for an ApiError', () => {
    expect(failure(new ApiError(422, NO_RUN, null))).toEqual({ kind: 'error', message: `${NO_RUN}\n${TERMINAL_HINT}` })
  })

  it('the hint text is the agreed copy', () => {
    expect(TERMINAL_HINT).toBe(
      'The app may have lost its Terminal window. Close it and start the app again from webapp/start.command.',
    )
  })
})
