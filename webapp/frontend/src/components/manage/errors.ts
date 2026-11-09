import { ApiError } from '../../api/client'
import type { Conflict409, Risk } from '../../api/types'
import { visible } from '../../lib/visible'

export const STALE_TEXT = 'This risk changed after you opened it. Review the current version.'

export type Failure = { kind: 'stale'; current: Risk | null } | { kind: 'error'; message: string }

/** Turn a failed request into what the form shows; core's text is escaped (ruling R16). */
export function failure(e: unknown): Failure {
  if (e instanceof ApiError && e.status === 409) {
    return { kind: 'stale', current: (e.body as Conflict409 | null)?.current ?? null }
  }
  return { kind: 'error', message: visible(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)) }
}
