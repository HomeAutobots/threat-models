import { Table } from '@mantine/core'
import type { Risk } from '../../api/types'
import type { Meta } from '../../api/types'
import { formatCategory } from '../../lib/format'
import { visible } from '../../lib/visible'
import { FieldValue, WRAP_STYLE } from './FieldValue'

const ROWS: [string, string][] = [
  ['title', 'Title'],
  ['elements', 'Elements'],
  ['category', 'Category'],
  ['description', 'Description'],
  ['attack_scenario', 'Attack scenario'],
]

function cell(risk: Risk, field: string, meta: Meta) {
  if (field === 'category') {
    return <FieldValue field={field} value={formatCategory(risk.category, meta)} />
  }
  return <FieldValue field={field} value={risk[field]} />
}

export function DuplicateCompare({ risk, other, meta }: { risk: Risk; other: Risk; meta: Meta }) {
  return (
    <Table verticalSpacing="xs">
      <Table.Thead>
        <Table.Tr>
          <Table.Th w={160}>Field</Table.Th>
          <Table.Th style={WRAP_STYLE}>{visible(risk.id)} (this risk)</Table.Th>
          <Table.Th style={WRAP_STYLE}>{visible(other.id)}</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {ROWS.map(([field, label]) => (
          <Table.Tr key={field}>
            <Table.Td>{label}</Table.Td>
            <Table.Td>{cell(risk, field, meta)}</Table.Td>
            <Table.Td>{cell(other, field, meta)}</Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
}
