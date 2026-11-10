import { Badge, Group, Table, Text } from '@mantine/core'
import type { ModelApproval, ModelState } from '../../api/types'
import { formatActor, formatTime } from '../../lib/format'
import { visible } from '../../lib/visible'

interface Props {
  state: ModelState
  latest: ModelApproval | null
  approvals: ModelApproval[]
}

const COLOR: Record<ModelState, string> = { current: 'green', changed: 'yellow', none: 'gray' }

export function ModelStatus({ state, latest, approvals }: Props) {
  return (
    <>
      <Group gap="xs">
        <Text size="sm">File against the latest approval:</Text>
        <Badge color={COLOR[state]}>{state}</Badge>
        {latest?.version && <Text size="sm">Approved version {visible(latest.version)}</Text>}
      </Group>
      {approvals.length > 0 && (
        <Table.ScrollContainer minWidth={500}>
          <Table aria-label="Approvals">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>ID</Table.Th>
                <Table.Th>Version</Table.Th>
                <Table.Th>Approved by</Table.Th>
                <Table.Th>When</Table.Th>
                <Table.Th>Note</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {approvals.map((a) => (
                <Table.Tr key={a.id}>
                  <Table.Td>{visible(a.id)}</Table.Td>
                  <Table.Td>{visible(a.version ?? '')}</Table.Td>
                  <Table.Td>{visible(formatActor(a.approved_by))}</Table.Td>
                  <Table.Td>{formatTime(a.approved_at)}</Table.Td>
                  <Table.Td style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{visible(a.note ?? '')}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </>
  )
}
