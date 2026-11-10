import { Badge, Group, Table, Text } from '@mantine/core'
import type { C4Item, C4Rel, C4View, CitedItem, ModelEntry, ModelInfo } from '../../api/types'
import { visible } from '../../lib/visible'
import { NotProvided, WRAP_STYLE } from './FieldValue'

export function elementCaption(model: ModelInfo): string {
  if (model.basis === 'dfd') return 'Written before the C4 model; IDs as written.'
  if (model.moved_on) return `Written against ${model.written_against ?? 'an unknown version'}; the latest is ${model.latest_id ?? 'none'}`
  return `From ${model.written_against ?? model.latest_id ?? 'the model'} (current)`
}

const isRel = (e: ModelEntry): e is C4Rel => 'source' in e
const isView = (e: ModelEntry): e is C4View => 'steps' in e

function Line({ label, children }: { label?: string; children: string }) {
  return (
    <div style={WRAP_STYLE}>
      {label && (
        <Text component="span" size="xs" c="dimmed">
          {label}{' '}
        </Text>
      )}
      <span>{visible(children)}</span>
    </div>
  )
}

function Item({ e }: { e: C4Item }) {
  return (
    <>
      <Group gap={6}>
        <Badge variant="default" tt="none">
          {visible(e.kind)}
        </Badge>
        {e.where.length > 0 && (
          <Text size="xs" c="dimmed" ff="monospace">
            {visible(e.where.join(' › '))}
          </Text>
        )}
      </Group>
      <Text fw={600} inherit style={WRAP_STYLE}>
        {visible(e.name)}
      </Text>
      {e.technology && <Line>{e.technology}</Line>}
      {e.description && <Line>{e.description}</Line>}
      {e.role && <Line>{e.role}</Line>}
    </>
  )
}

function Rel({ e }: { e: C4Rel }) {
  const p = e.properties ?? {}
  return (
    <>
      <Text fw={600} inherit style={WRAP_STYLE}>
        {visible(`${e.source} → ${e.destination}`)}
      </Text>
      {e.technology && <Line>{e.technology}</Line>}
      {e.description && <Line>{e.description}</Line>}
      {e.role && <Line>{e.role}</Line>}
      {p['tm.data.sent'] && <Line label="Sent">{p['tm.data.sent']}</Line>}
      {p['tm.data.returned'] && <Line label="Returned">{p['tm.data.returned']}</Line>}
      {p['tm.auth'] && <Line label="Auth">{p['tm.auth']}</Line>}
      {Object.entries(e.crossings ?? {}).map(([env, tbs]) => (
        <Line key={env} label="Crosses">{`${env}: ${tbs.join(', ')}`}</Line>
      ))}
    </>
  )
}

function View({ e }: { e: C4View }) {
  return (
    <>
      <Badge variant="default" tt="none">
        {visible(e.kind)}
      </Badge>
      <Text fw={600} inherit style={WRAP_STYLE}>
        {visible(e.title ?? '')}
      </Text>
      {e.steps.map((s, i) => (
        <Line key={i}>{s}</Line>
      ))}
    </>
  )
}

function Entry({ e }: { e: ModelEntry }) {
  return isRel(e) ? <Rel e={e} /> : isView(e) ? <View e={e} /> : <Item e={e} />
}

function Details({ c, model }: { c: CitedItem; model: ModelInfo }) {
  if (c.state === 'dfd' || !c.written) return <NotProvided text="IDs as written" />
  if (c.state === 'changed' && c.latest) {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
        <div>
          <Text size="xs" fw={600} c="dimmed" tt="uppercase">
            As written
          </Text>
          <Entry e={c.written} />
        </div>
        <div>
          <Text size="xs" fw={600} c="dimmed" tt="uppercase">
            Now
          </Text>
          <Entry e={c.latest} />
        </div>
      </div>
    )
  }
  return (
    <>
      {c.state === 'removed' && (
        <Badge color="red" variant="light" tt="none" mb={4}>
          {visible(`Removed in ${model.latest_id ?? 'the latest model'}`)}
        </Badge>
      )}
      <Entry e={c.written} />
    </>
  )
}

export function ElementTable({
  ids,
  elements,
  model,
}: {
  ids: string[]
  elements: Record<string, CitedItem>
  model: ModelInfo
}) {
  if (ids.length === 0) return <NotProvided />
  return (
    <Table verticalSpacing="xs">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>ID</Table.Th>
          <Table.Th>What the model says</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {ids.map((id) => {
          const c = elements[id] ?? { written: null, latest: null, state: 'dfd' as const }
          return (
            <Table.Tr key={id}>
              <Table.Td>
                <Text component="span" ff="monospace" size="sm" style={WRAP_STYLE}>
                  {visible(id)}
                </Text>
              </Table.Td>
              <Table.Td style={WRAP_STYLE}>
                <Details c={c} model={model} />
              </Table.Td>
            </Table.Tr>
          )
        })}
      </Table.Tbody>
    </Table>
  )
}
