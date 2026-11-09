import { Badge, Card, Group, Table, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import type { Change, Meta, Risk, RiskDetail } from '../../api/types'
import { formatActor, formatCategory, formatTime } from '../../lib/format'
import { visible } from '../../lib/visible'
import { DuplicateCompare } from './DuplicateCompare'
import { ElementTable, elementCaption } from './ElementTable'
import { FieldValue, NotProvided, WRAP_STYLE } from './FieldValue'
import { FIELD_LABELS, SECTIONS, type Section } from './sections'

const OP_LABELS: Record<string, string> = {
  add: 'Added',
  edit: 'Edited',
  approve: 'Approved',
  reject: 'Rejected',
  merge: 'Merged',
  retire: 'Retired',
}

const STATE_LABELS: Record<string, string> = {
  pending: 'Pending review',
  approved: 'Approved',
  rejected: 'Rejected',
}

/** The sections a risk shows: section 8 only when a possible duplicate is set. */
export function visibleSections(risk: Risk): Section[] {
  return SECTIONS.filter((s) => s.id !== 'dup' || !!risk.possible_duplicate_of)
}

function Heading({ s, suffix }: { s: Section; suffix?: ReactNode }) {
  return (
    <Group gap="xs" align="baseline" mb="sm" wrap="wrap">
      <Text size="sm" c="dimmed">
        {s.n}
      </Text>
      <Title order={2} size="sm" tt="uppercase" c="dimmed" style={{ letterSpacing: '0.06em', ...WRAP_STYLE }}>
        {s.title}
      </Title>
      {suffix}
    </Group>
  )
}

function Fields({ fields, display }: { fields: string[]; display: (f: string) => unknown }) {
  return (
    <dl style={{ display: 'grid', gridTemplateColumns: 'minmax(120px, 200px) minmax(0, 1fr)', gap: '10px 18px', margin: 0 }}>
      {fields.map((f) => (
        <FieldRow key={f} field={f} value={display(f)} />
      ))}
    </dl>
  )
}

function FieldRow({ field, value }: { field: string; value: unknown }) {
  return (
    <>
      <Text component="dt" size="sm" fw={600} c="dimmed">
        {FIELD_LABELS[field] ?? field}
      </Text>
      <dd style={{ margin: 0, maxWidth: '75ch', minWidth: 0 }}>
        <FieldValue field={field} value={value} />
      </dd>
    </>
  )
}

export function RiskRecord({ detail, meta, history }: { detail: RiskDetail; meta: Meta; history: Change[] }) {
  const { risk } = detail
  const display = (f: string): unknown => (f === 'category' ? formatCategory(risk.category, meta) : risk[f])
  const pending = risk.review_state === 'pending'
  const secs = visibleSections(risk)

  const body = (s: Section): ReactNode => {
    switch (s.id) {
      case 'glance':
        return (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 12 }}>
              {s.fields.map((f) => (
                <Card key={f} withBorder padding="xs" radius="md">
                  <Text size="xs" c="dimmed">
                    {FIELD_LABELS[f]}
                  </Text>
                  <Text fw={600} component="div">
                    <FieldValue field={f} value={display(f)} />
                  </Text>
                </Card>
              ))}
            </div>
            <Text size="sm" c="dimmed" mt="sm">
              A quick orientation only. Every field is below in full, including the empty ones.
            </Text>
          </>
        )
      case 'where':
        return <ElementTable ids={risk.elements ?? []} elements={detail.elements} dfd={detail.dfd} />
      case 'threat':
        return (
          <>
            {s.fields.map((f) => (
              <div key={f} style={{ marginBottom: 16 }}>
                <Text size="xs" fw={600} c="dimmed" tt="uppercase">
                  {FIELD_LABELS[f]}
                </Text>
                <div style={{ maxWidth: '75ch' }}>
                  <FieldValue field={f} value={risk[f]} />
                </div>
              </div>
            ))}
          </>
        )
      case 'dup':
        return detail.duplicate ? (
          <DuplicateCompare risk={risk} other={detail.duplicate} meta={meta} />
        ) : (
          <Fields fields={s.fields} display={display} />
        )
      case 'record':
        return (
          <>
            <Fields fields={s.fields} display={display} />
            <Text size="xs" fw={600} c="dimmed" tt="uppercase" mt="md" mb="xs">
              History
            </Text>
            <HistoryTable history={history} />
          </>
        )
      default:
        return <Fields fields={s.fields} display={display} />
    }
  }

  return (
    <div>
      <Title order={1} size="h2" mb="xs" style={WRAP_STYLE}>
        <Text component="span" ff="monospace" size="sm" bg="var(--mantine-color-default-hover)" px={6} mr="xs">
          {visible(risk.id)}
        </Text>
        {risk.title ? visible(risk.title) : <NotProvided />}
      </Title>
      <Group gap={6} mb="md">
        <Badge variant={pending ? 'light' : 'default'} color={pending ? 'yellow' : undefined}>
          {STATE_LABELS[risk.review_state] ?? visible(String(risk.review_state))}
        </Badge>
        {pending && <Badge variant="default">{risk.last_approved ? 'Re-review' : 'New draft'}</Badge>}
        {risk.drafted_by && (
          <Badge variant="light" tt="none">
            {visible(`Drafted by ${formatActor(risk.drafted_by)}`)}
          </Badge>
        )}
        {risk.ai_confidence && (
          <Badge variant="default" tt="none">
            {visible(`AI confidence: ${risk.ai_confidence}`)}
          </Badge>
        )}
      </Group>
      {secs.map((s) => (
        <Card
          key={s.id}
          component="section"
          id={s.id}
          withBorder
          radius="md"
          padding="lg"
          mb="md"
          style={{ scrollMarginTop: 70 }}
        >
          <Heading
            s={s}
            suffix={
              s.id === 'where' ? (
                <Text size="xs" c="dimmed" component="span">
                  {'·'} {visible(elementCaption(detail.dfd))}
                </Text>
              ) : s.id === 'dup' ? (
                <Text size="sm" component="span" fw={600}>
                  {visible(String(risk.possible_duplicate_of))}
                </Text>
              ) : undefined
            }
          />
          {body(s)}
        </Card>
      ))}
    </div>
  )
}

function HistoryTable({ history }: { history: Change[] }) {
  if (history.length === 0) return <NotProvided text="No history yet" />
  return (
    <Table verticalSpacing="xs">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>#</Table.Th>
          <Table.Th>When</Table.Th>
          <Table.Th>Who</Table.Th>
          <Table.Th>What</Table.Th>
          <Table.Th>Note</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {history.map((c) => (
          <Table.Tr key={c.seq}>
            <Table.Td>{c.seq}</Table.Td>
            <Table.Td>{formatTime(c.at)}</Table.Td>
            <Table.Td style={WRAP_STYLE}>{visible(formatActor(c.actor))}</Table.Td>
            <Table.Td>{OP_LABELS[c.op] ?? visible(c.op)}</Table.Td>
            <Table.Td style={WRAP_STYLE}>{c.note ? visible(c.note) : <NotProvided text="none" />}</Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
}
