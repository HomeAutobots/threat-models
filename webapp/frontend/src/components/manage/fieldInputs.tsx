import { Select, TagsInput, Textarea } from '@mantine/core'
import type { Meta, Risk } from '../../api/types'
import { FIELD_LABELS, SECTIONS } from '../record/sections'

export type FormValue = string | string[]
export type FormValues = Record<string, FormValue>

const LIST_FIELDS = new Set(['elements', 'control_refs'])
const SELECT_FIELDS = new Set(['category', 'method', 'origin', 'treatment', 'ai_confidence', 'status'])

/** The IDs a risk cites are the C4 model's, not DFD IDs. */
export const ELEMENTS_HINT = 'Item and path IDs from the approved C4 model, such as C2, K1 or R1.'

export const isList = (field: string) => LIST_FIELDS.has(field)

/** A stored value as the form holds it: text as a string, lists as string arrays. */
export function toForm(field: string, value: unknown): FormValue {
  if (isList(field)) return Array.isArray(value) ? value.map(String) : []
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.map(String).join('\n')
  return String(value)
}

export function sameValue(a: FormValue, b: FormValue): boolean {
  return Array.isArray(a) && Array.isArray(b)
    ? a.length === b.length && a.every((x, i) => x === b[i])
    : a === b
}

/** The editable fields, in the order of the full-record view; `title` leads. */
export function groupedFields(editable: string[]): { title: string; fields: string[] }[] {
  const left = new Set(editable)
  const groups: { title: string; fields: string[] }[] = []
  const take = (title: string, fields: string[]) => {
    const mine = fields.filter((f) => left.has(f))
    mine.forEach((f) => left.delete(f))
    if (mine.length) groups.push({ title, fields: mine })
  }
  take('Title', ['title'])
  for (const s of SECTIONS) take(s.title, s.fields)
  take('Other', [...left])
  return groups
}

function humanize(field: string): string {
  const words = field.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export function fieldLabel(meta: Meta, field: string): string {
  return meta.labels?.[field] ?? FIELD_LABELS[field] ?? humanize(field)
}

function optionsFor(field: string, meta: Meta, current: string): { value: string; label: string }[] {
  let options: { value: string; label: string }[] = []
  if (field === 'category') {
    options = [
      ...Object.entries(meta.stride).map(([k, name]) => ({ value: k, label: `${k} - ${name}` })),
      ...meta.linddun.map((n) => ({ value: n, label: n })),
    ]
  } else {
    const list =
      field === 'method'
        ? meta.methods
        : field === 'origin'
          ? meta.origins
          : field === 'treatment'
            ? meta.treatments
            : field === 'ai_confidence'
              ? meta.confidence
              : meta.statuses
    options = (list ?? []).map((v) => ({ value: v, label: v }))
  }
  // A stored value the lists do not know still shows, so opening the form never hides it.
  if (current && !options.some((o) => o.value === current)) options.push({ value: current, label: current })
  return options
}

interface Props {
  field: string
  meta: Meta
  value: FormValue
  required: boolean
  disabled: boolean
  onChange: (value: FormValue) => void
}

export function FieldInput({ field, meta, value, required, disabled, onChange }: Props) {
  const label = fieldLabel(meta, field)
  if (isList(field)) {
    return (
      <TagsInput
        label={label}
        description={field === 'elements' ? ELEMENTS_HINT : undefined}
        required={required}
        disabled={disabled}
        value={value as string[]}
        onChange={onChange}
        clearable
        splitChars={[',']}
        placeholder="Type, then Enter"
      />
    )
  }
  if (SELECT_FIELDS.has(field)) {
    return (
      <Select
        label={label}
        required={required}
        disabled={disabled}
        data={optionsFor(field, meta, value as string)}
        value={(value as string) || null}
        onChange={(v) => onChange(v ?? '')}
        clearable
        allowDeselect
      />
    )
  }
  return (
    <Textarea
      label={label}
      required={required}
      disabled={disabled}
      autosize
      minRows={field === 'title' ? 1 : 2}
      value={value as string}
      onChange={(e) => onChange(e.currentTarget.value)}
      styles={{ input: { overflowWrap: 'anywhere' } }}
    />
  )
}

/** Fields that differ from `seen`, as the API takes them: `""` for cleared text, `[]` for a cleared list. */
export function changedFields(editable: string[], values: FormValues, seen: Risk): FormValues {
  const out: FormValues = {}
  for (const f of editable) {
    if (!sameValue(values[f], toForm(f, seen[f]))) out[f] = values[f]
  }
  return out
}
