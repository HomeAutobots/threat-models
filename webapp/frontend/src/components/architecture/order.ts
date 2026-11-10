import { visible } from '../../lib/visible'

const KINDS = ['A', 'S', 'C', 'K', 'R', 'TB', 'N', 'I', 'ENV', 'SEQ']

export const prefix = (id: string) => /^[A-Z]+/.exec(id)?.[0] ?? ''
const num = (id: string) => Number(/\d+$/.exec(id)?.[0] ?? 0)
const rank = (id: string) => {
  const i = KINDS.indexOf(prefix(id))
  return i < 0 ? KINDS.length : i
}

/** Kind order (A, S, C, K, R, TB, N, I, ENV, SEQ), then number. */
export const byId = (a: string, b: string) => rank(a) - rank(b) || num(a) - num(b) || a.localeCompare(b)

/** "C2 API": the name already starts with its ID in a real model, so the ID is not repeated. */
export const idName = (id: string, name: string) => visible(name.startsWith(id) ? name : `${id} ${name}`)
