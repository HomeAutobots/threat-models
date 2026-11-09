import { Alert, List, Loader, Stack, Table, Text, Title } from '@mantine/core'
import { useParams } from 'react-router'
import { useHistory, useVerify } from '../api/queries'
import type { Reg } from '../api/types'
import { formatActor, formatTime } from '../lib/format'
import { visible } from '../lib/visible'

export function HistoryPage() {
  const { reg, slug } = useParams()
  const history = useHistory(reg as Reg, slug as string)
  const verify = useVerify(reg as Reg, slug as string)

  return (
    <Stack>
      <Title order={1} size="h3">
        History
      </Title>
      {verify.isLoading ? (
        <Loader size="sm" aria-label="Verifying" />
      ) : verify.error ? (
        <Alert color="red">{visible(verify.error.message)}</Alert>
      ) : verify.data && verify.data.problems.length === 0 ? (
        <Alert color="green">Change log verified: the hash chain and stored rows match.</Alert>
      ) : (
        <Alert color="red" title="The change log has problems">
          <List>
            {(verify.data?.problems ?? []).map((p, i) => (
              <List.Item key={i} style={{ overflowWrap: 'anywhere' }}>
                {visible(p)}
              </List.Item>
            ))}
          </List>
        </Alert>
      )}
      {history.isLoading ? (
        <Loader aria-label="Loading" />
      ) : history.error ? (
        <Alert color="red">{visible(history.error.message)}</Alert>
      ) : (history.data ?? []).length === 0 ? (
        <Text>No changes yet.</Text>
      ) : (
        <Table.ScrollContainer minWidth={600}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>#</Table.Th>
                <Table.Th>When</Table.Th>
                <Table.Th>Who</Table.Th>
                <Table.Th>What</Table.Th>
                <Table.Th>Row</Table.Th>
                <Table.Th>Note</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(history.data ?? []).map((c) => (
                <Table.Tr key={c.seq}>
                  <Table.Td>{c.seq}</Table.Td>
                  <Table.Td>{formatTime(c.at)}</Table.Td>
                  <Table.Td>{visible(formatActor(c.actor))}</Table.Td>
                  <Table.Td>{visible(c.op)}</Table.Td>
                  <Table.Td>{visible(`${c.tbl} / ${c.row_key}`)}</Table.Td>
                  <Table.Td style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{visible(c.note ?? '')}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Stack>
  )
}
