import { Text } from '@mantine/core'
import { formatActor, formatTime } from '../../lib/format'
import { visible } from '../../lib/visible'

/** Long text is never clamped, truncated, or ellipsized. */
export const WRAP_STYLE = { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' } as const

const ACTOR_FIELDS = new Set(['drafted_by', 'reviewed_by'])

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0)
}

export function NotProvided({ text = 'Not provided' }: { text?: string }) {
  return (
    <Text span c="dimmed" fs="italic" inherit>
      {text}
    </Text>
  )
}

function display(value: unknown, field: string): string {
  if (Array.isArray(value)) return value.map((v) => String(v)).join('; ')
  if (field.endsWith('_at') && typeof value === 'string') return formatTime(value)
  if (ACTOR_FIELDS.has(field) && typeof value === 'string') return formatActor(value)
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number' && field === 'detail_complete') return value ? 'Yes' : 'No'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export function FieldValue({ value, field }: { value: unknown; field: string }) {
  if (field === 'last_approved') {
    return value === null || value === undefined ? (
      <NotProvided text="None" />
    ) : (
      <span style={WRAP_STYLE}>Kept while this re-review is pending</span>
    )
  }
  if (isEmpty(value)) return <NotProvided />
  return <span style={WRAP_STYLE}>{visible(display(value, field))}</span>
}
