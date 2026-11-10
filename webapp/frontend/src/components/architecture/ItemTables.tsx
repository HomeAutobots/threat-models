import { Stack, Table, Text, Title, UnstyledButton } from '@mantine/core'
import type { ReactNode } from 'react'
import type { C4Item, C4Record, C4Rel, C4View } from '../../api/types'
import { visible } from '../../lib/visible'

interface Props {
  record: C4Record
  counts: Record<string, { open: number; pending: number }>
  selected: string | null
  onSelect: (id: string) => void
}

const prefix = (id: string) => /^[A-Z]+/.exec(id)?.[0] ?? ''
const num = (id: string) => Number(/\d+$/.exec(id)?.[0] ?? 0)
const byId = (a: string, b: string) => num(a) - num(b) || a.localeCompare(b)

function crossingText(r: C4Rel): string {
  return Object.entries(r.crossings)
    .filter(([, tbs]) => tbs.length > 0)
    .map(([env, tbs]) => `${env}: ${tbs.join(', ')}`)
    .join('\n')
}

interface Col<T> {
  head: string
  cell: (id: string, v: T) => ReactNode
}

function Section<T>({
  title,
  rows,
  cols,
  counts,
  selected,
  onSelect,
  heading = 'h3',
}: {
  title: string
  rows: [string, T][]
  cols: Col<T>[]
  counts: Props['counts']
  selected: string | null
  onSelect: (id: string) => void
  heading?: 'h3' | 'h4'
}) {
  if (rows.length === 0) return null
  const size = heading === 'h3' ? 'h4' : 'h5'
  return (
    <Stack gap="xs">
      <Title order={heading === 'h3' ? 3 : 4} size={size}>
        {title}
      </Title>
      <Table.ScrollContainer minWidth={600}>
        <Table aria-label={title} highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>ID</Table.Th>
              {cols.map((c) => (
                <Table.Th key={c.head}>{c.head}</Table.Th>
              ))}
              <Table.Th>Risks</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map(([id, v]) => {
              const n = counts[id]
              return (
                <Table.Tr key={id} bg={selected === id ? 'var(--mantine-color-blue-light)' : undefined}>
                  <Table.Td>
                    <UnstyledButton
                      onClick={() => onSelect(id)}
                      aria-pressed={selected === id}
                      aria-label={`Select ${id}`}
                      fw={600}
                    >
                      {visible(id)}
                    </UnstyledButton>
                  </Table.Td>
                  {cols.map((c) => (
                    <Table.Td key={c.head} style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                      {c.cell(id, v)}
                    </Table.Td>
                  ))}
                  <Table.Td>
                    {n ? [n.open > 0 && `${n.open} open`, n.pending > 0 && `${n.pending} pending`].filter(Boolean).join(', ') : ''}
                  </Table.Td>
                </Table.Tr>
              )
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Stack>
  )
}

export function ItemTables({ record, counts, selected, onSelect }: Props) {
  const items = Object.entries(record.items)
  const of = (...kinds: string[]) =>
    items.filter(([id]) => kinds.includes(prefix(id))).sort(([a], [b]) => byId(a, b)) as [string, C4Item][]
  const t = (s: string | null | undefined) => visible(s ?? '')
  const prop = (it: C4Item, key: string) => t(it.properties[key])
  const common = { counts, selected, onSelect }

  const paths = Object.entries(record.rels).sort(([a], [b]) => byId(a, b))
  const seqs = (Object.entries(record.views) as [string, C4View][])
    .filter(([, v]) => v.kind === 'dynamic')
    .sort(([a], [b]) => byId(a, b))
  const boundaries = of('TB')
  const components = of('K')
  const containers = of('C')
  const inside = (tb: string) =>
    items
      .filter(([, it]) => it.parent === tb || it.group === tb)
      .map(([id]) => id)
      .sort(byId)
      .join(', ')
  const crossedBy = (tb: string) =>
    paths
      .filter(([, r]) => Object.values(r.crossings).some((tbs) => tbs.includes(tb)))
      .map(([id]) => id)
      .join(', ')

  return (
    <Stack>
      <Section
        title="People and systems"
        rows={of('A', 'S')}
        {...common}
        cols={[
          { head: 'Name', cell: (_, v) => t(v.name) },
          { head: 'Description', cell: (_, v) => t(v.description) },
          { head: 'Role', cell: (_, v) => t(v.role) },
        ]}
      />
      <Section
        title="Containers"
        rows={containers}
        {...common}
        cols={[
          { head: 'Name', cell: (_, v) => t(v.name) },
          { head: 'Role', cell: (_, v) => t(v.role) },
          { head: 'Technology', cell: (_, v) => t(v.technology) },
          { head: 'Owner', cell: (_, v) => prop(v, 'tm.owner') },
          { head: 'Zoom reason', cell: (_, v) => prop(v, 'tm.zoom') },
        ]}
      />
      {containers
        .map(([id]) => [id, components.filter(([, k]) => k.parent === id)] as const)
        .filter(([, ks]) => ks.length > 0)
        .map(([cid, ks]) => (
          <Section
            key={cid}
            heading="h4"
            title={`Components of ${visible(cid)} ${visible(record.items[cid].name)}`}
            rows={ks}
            {...common}
            cols={[
              { head: 'Name', cell: (_, v) => t(v.name) },
              { head: 'Role', cell: (_, v) => t(v.role) },
              { head: 'Technology', cell: (_, v) => t(v.technology) },
              { head: 'Owner', cell: (_, v) => prop(v, 'tm.owner') },
            ]}
          />
        ))}
      <Section
        title="Paths"
        rows={paths}
        {...common}
        cols={[
          { head: 'From → To', cell: (_, v) => t(`${v.source} → ${v.destination}`) },
          { head: 'Description', cell: (_, v) => t(v.description) },
          { head: 'Technology', cell: (_, v) => t(v.technology) },
          { head: 'Data sent', cell: (_, v) => t(v.properties['tm.data.sent']) },
          { head: 'Data returned', cell: (_, v) => t(v.properties['tm.data.returned']) },
          { head: 'Authentication', cell: (_, v) => t(v.properties['tm.auth']) },
          { head: 'Crosses', cell: (_, v) => t(crossingText(v)) },
        ]}
      />
      <Section
        title="Trust boundaries"
        rows={boundaries}
        {...common}
        cols={[
          { head: 'Name', cell: (_, v) => t(v.name) },
          { head: 'Inside', cell: (id) => t(inside(id)) },
          { head: 'Enforced by', cell: (_, v) => prop(v, 'tm.enforced_by') },
          { head: 'Crossed by', cell: (id) => t(crossedBy(id)) },
        ]}
      />
      <Section
        title="Deployment and infrastructure"
        rows={of('N', 'I')}
        {...common}
        cols={[
          { head: 'Name', cell: (_, v) => t(v.name) },
          { head: 'Technology', cell: (_, v) => t(v.technology) },
          { head: 'Within', cell: (_, v) => t(v.where.slice(0, -1).join(' › ')) },
        ]}
      />
      <Section
        title="Sequences"
        rows={seqs}
        {...common}
        cols={[
          { head: 'Title', cell: (_, v) => t(v.title) },
          { head: 'Steps', cell: (_, v) => t(v.steps.map((s, i) => `${i + 1}. ${s}`).join('\n')) },
        ]}
      />
      {items.length === 0 && paths.length === 0 && seqs.length === 0 && <Text size="sm">The model has no items.</Text>}
    </Stack>
  )
}
