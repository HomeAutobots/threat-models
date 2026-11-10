import { Anchor, Card, List, Stack, Text, Title } from '@mantine/core'
import { Link } from 'react-router'
import type { C4Item, C4Record, C4Rel, C4View, Reg, Risk } from '../../api/types'
import { visible } from '../../lib/visible'

interface Props {
  reg: Reg
  slug: string
  id: string
  record: C4Record
  risks: Risk[]
}

function text(v: unknown, joiner = ', '): string {
  if (v === null || v === undefined) return ''
  if (Array.isArray(v)) return v.map((x) => text(x)).join(joiner)
  if (typeof v === 'object')
    return Object.entries(v as Record<string, unknown>)
      .map(([k, x]) => `${k}: ${text(x)}`)
      .join('\n')
  return String(v)
}

const LABELS: [string, string][] = [
  ['kind', 'Kind'],
  ['role', 'Role'],
  ['name', 'Name'],
  ['title', 'Title'],
  ['scope', 'Scope'],
  ['source', 'From'],
  ['destination', 'To'],
  ['description', 'Description'],
  ['technology', 'Technology'],
  ['tags', 'Tags'],
  ['where', 'Where'],
  ['properties', 'Properties'],
  ['zones', 'Zones'],
  ['crossings', 'Crossings'],
  ['steps', 'Steps'],
]

const live = (r: Risk) => r.review_state !== 'rejected' && r.status !== 'retired' && !r.merged_into

function RiskList({ reg, slug, risks }: { reg: Reg; slug: string; risks: Risk[] }) {
  return (
    <List size="sm">
      {risks.map((r) => (
        <List.Item key={r.id}>
          <Anchor component={Link} to={`/${reg}/${encodeURIComponent(slug)}/risks/${encodeURIComponent(r.id)}`}>
            {visible(r.id)}
          </Anchor>{' '}
          {visible(r.title ?? '')}
          {r.status ? ` (${visible(String(r.status))})` : ''}
        </List.Item>
      ))}
    </List>
  )
}

export function ItemDetail({ reg, slug, id, record, risks }: Props) {
  const entry = (record.items[id] ?? record.rels[id] ?? record.views[id]) as C4Item | C4Rel | C4View | undefined
  if (!entry) return null
  const fields = LABELS.filter(([k]) => {
    const v = (entry as unknown as Record<string, unknown>)[k]
    return v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0) &&
      !(typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 0)
  })

  // The item and everything inside it, plus the paths that start or end in that set (or, for a
  // trust boundary, cross it).
  const own = new Set([id, ...Object.entries(record.items).filter(([, it]) => it.where.includes(id)).map(([k]) => k)])
  const paths = Object.entries(record.rels)
    .filter(
      ([, r]) =>
        own.has(r.source) || own.has(r.destination) || Object.values(r.crossings).some((tbs) => tbs.includes(id)),
    )
    .map(([k]) => k)
  const related = new Set([...own, ...paths])
  related.delete(id)

  const cites = (r: Risk, ids: Set<string>) => (r.elements ?? []).some((e) => ids.has(e))
  const liveRisks = risks.filter(live)
  const direct = liveRisks.filter((r) => cites(r, new Set([id])))
  const nearby = liveRisks.filter((r) => !direct.includes(r) && cites(r, related))

  return (
    <Card withBorder component="section" aria-label={`Details of ${id}`}>
      <Stack gap="xs">
        <Title order={3} size="h4">
          {visible(id)} {visible((entry as { name?: string }).name ?? '')}
        </Title>
        {fields.map(([k, label]) => (
          <div key={k}>
            <Text size="xs" c="dimmed">
              {label}
            </Text>
            <Text size="sm" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
              {visible(text((entry as unknown as Record<string, unknown>)[k], k === 'where' ? ' › ' : ', '))}
            </Text>
          </div>
        ))}
        {direct.length > 0 && (
          <>
            <Title order={4} size="h5">
              Risks on {visible(id)}
            </Title>
            <RiskList reg={reg} slug={slug} risks={direct} />
          </>
        )}
        {nearby.length > 0 && (
          <>
            <Title order={4} size="h5">
              Risks on its paths and components
            </Title>
            <RiskList reg={reg} slug={slug} risks={nearby} />
          </>
        )}
      </Stack>
    </Card>
  )
}
