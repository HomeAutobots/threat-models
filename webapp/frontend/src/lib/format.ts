import type { Meta } from '../api/types'

const pad = (n: number) => String(n).padStart(2, '0')

/** Local `YYYY-MM-DD HH:mm`. */
export function formatTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function formatActor(actor: string | null): string {
  if (!actor) return ''
  if (actor.startsWith('ai:')) return `AI, run ${actor.slice(3)}`
  if (actor === 'human:catalog-import') return 'Catalog import'
  if (actor.startsWith('human:')) return actor.slice(6)
  return actor
}

export function formatCategory(c: string | null, meta: Meta): string {
  if (!c) return ''
  if (meta.stride[c]) return `${meta.stride[c]} (STRIDE ${c})`
  if (meta.linddun.includes(c)) return `${c} (LINDDUN)`
  return c
}
