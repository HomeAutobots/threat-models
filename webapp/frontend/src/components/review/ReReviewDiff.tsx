import { Card, Table, Text, Title } from '@mantine/core'
import type { Risk } from '../../api/types'
import { FieldValue } from '../record/FieldValue'

function isEmpty(v: unknown): boolean {
  return v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0)
}

function same(a: unknown, b: unknown): boolean {
  if (isEmpty(a) && isEmpty(b)) return true
  return JSON.stringify(a) === JSON.stringify(b)
}

/** Only the editable fields whose proposed value differs from the last approved version. */
export function ReReviewDiff({
  risk,
  editable,
  labels,
}: {
  risk: Risk
  editable: string[]
  labels: Record<string, string>
}) {
  const approved = risk.last_approved
  if (!approved) return null
  const changed = editable.filter((f) => !same(approved[f], risk[f]))
  const unchanged = editable.length - changed.length

  return (
    <Card withBorder radius="md" padding="lg" mb="md">
      <Title order={2} size="sm" tt="uppercase" c="dimmed" mb="sm" style={{ letterSpacing: '0.06em' }}>
        What changed since the last approved version
      </Title>
      {changed.length > 0 && (
        <Table verticalSpacing="xs" style={{ tableLayout: 'fixed' }}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Field</Table.Th>
              <Table.Th>Last approved</Table.Th>
              <Table.Th>Proposed</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {changed.map((f) => (
              <Table.Tr key={f}>
                <Table.Td fw={600}>{labels[f] ?? f}</Table.Td>
                <Table.Td>
                  <FieldValue field={f} value={approved[f]} />
                </Table.Td>
                <Table.Td>
                  <FieldValue field={f} value={risk[f]} />
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      <Text size="sm" c="dimmed" mt="xs">
        {unchanged} other {unchanged === 1 ? 'field' : 'fields'} unchanged
      </Text>
    </Card>
  )
}
