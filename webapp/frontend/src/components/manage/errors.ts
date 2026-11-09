import { ApiError } from '../../api/client'
import type { Conflict409, Risk } from '../../api/types'
import { visible } from '../../lib/visible'

export const STALE_TEXT = 'This risk changed after you opened it. Review the current version.'

export const TERMINAL_HINT =
  'The app may have lost its Terminal window. Close it and start the app again from webapp/start.command.'

/** Core's message, escaped; for the human-only and no-run refusals, the Terminal hint follows it. */
export function refusalText(detail: string): string {
  const text = visible(detail)
  return detail.includes('interactive terminal') || detail.includes('--run') ? `${text}\n${TERMINAL_HINT}` : text
}

export type Failure = { kind: 'stale'; current: Risk | null } | { kind: 'error'; message: string }

/** Turn a failed request into what the form shows; core's text is escaped (ruling R16). */
export function failure(e: unknown): Failure {
  if (e instanceof ApiError && e.status === 409) {
    return { kind: 'stale', current: (e.body as Conflict409 | null)?.current ?? null }
  }
  return { kind: 'error', message: refusalText(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)) }
}

/** The same record by content: the server sends fields in one order, so JSON text is enough. */
export function sameRecord(a: Risk, b: Risk): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}
