import { Table, Text } from '@mantine/core'
import type { DfdInfo, ElementDetail } from '../../api/types'
import { visible } from '../../lib/visible'
import { NotProvided, WRAP_STYLE } from './FieldValue'

const TYPE_LABELS: Record<string, string> = {
  process: 'Process',
  flow: 'Data flow',
  store: 'Data store',
  datastore: 'Data store',
  external: 'External entity',
  entity: 'External entity',
  boundary: 'Trust boundary',
}

export function elementCaption(dfd: DfdInfo): string {
  if (dfd.error) return `DFD details unavailable: ${dfd.error}`
  if (dfd.state === 'none') return 'No approved DFD yet'
  if (dfd.state === 'current' && dfd.latest_id === dfd.written_against) {
    return `From ${dfd.latest_id} (current)`
  }
  return `From the current dfd.md, which has changed since this risk was written against ${dfd.written_against}`
}

function text(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

export function ElementTable({
  ids,
  elements,
  dfd,
}: {
  ids: string[]
  elements: Record<string, ElementDetail | null>
  dfd: DfdInfo
}) {
  return (
    <>
      <Text size="sm" c="dimmed" mb="xs" style={WRAP_STYLE}>
        {visible(elementCaption(dfd))}
      </Text>
      {ids.length === 0 ? (
        <NotProvided />
      ) : (
        <Table verticalSpacing="xs">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>ID</Table.Th>
              <Table.Th>Element</Table.Th>
              <Table.Th>Type</Table.Th>
              <Table.Th>What the DFD says</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {ids.map((id) => {
              const el = elements[id] ?? null
              return (
                <Table.Tr key={id}>
                  <Table.Td>
                    <Text component="span" ff="monospace" size="sm" style={WRAP_STYLE}>
                      {visible(id)}
                    </Text>
                  </Table.Td>
                  {el === null ? (
                    <Table.Td colSpan={3}>
                      <Text c="dimmed" fs="italic" inherit>
                        Not in the current DFD
                      </Text>
                    </Table.Td>
                  ) : (
                    <>
                      <Table.Td style={WRAP_STYLE}>
                        {el.type === 'flow' && (text(el.from) || text(el.to)) ? (
                          <div>{visible(`${text(el.from)} → ${text(el.to)}`)}</div>
                        ) : null}
                        <div>{visible(el.name)}</div>
                      </Table.Td>
                      <Table.Td style={WRAP_STYLE}>{visible(TYPE_LABELS[el.type] ?? el.type)}</Table.Td>
                      <Table.Td style={WRAP_STYLE}>
                        {el.description ? visible(el.description) : <NotProvided />}
                      </Table.Td>
                    </>
                  )}
                </Table.Tr>
              )
            })}
          </Table.Tbody>
        </Table>
      )}
    </>
  )
}
