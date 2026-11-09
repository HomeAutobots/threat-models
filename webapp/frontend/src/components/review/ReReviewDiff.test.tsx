import { MantineProvider } from '@mantine/core'
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Risk } from '../../api/types'
import { ReReviewDiff } from './ReReviewDiff'

const labels = { title: 'Title', notes: 'Notes', impact: 'Impact', owner: 'Owner' }
const editable = ['title', 'notes', 'impact', 'owner']

function renderDiff(risk: Partial<Risk>) {
  render(
    <MantineProvider>
      <ReReviewDiff risk={risk as Risk} editable={editable} labels={labels} />
    </MantineProvider>,
  )
}

describe('ReReviewDiff', () => {
  it('diff shows only changed fields', () => {
    renderDiff({
      title: 'Same',
      notes: 'new note',
      impact: 'High',
      owner: null,
      last_approved: { title: 'Same', notes: 'old note', impact: 'High', owner: '' },
    })
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toEqual([
      'Field',
      'Last approved',
      'Proposed',
    ])
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows).toHaveLength(1)
    expect(within(rows[0]).getByText('Notes')).toBeInTheDocument()
    expect(within(rows[0]).getByText('old note')).toBeInTheDocument()
    expect(within(rows[0]).getByText('new note')).toBeInTheDocument()
    expect(screen.getByText('3 other fields unchanged')).toBeInTheDocument()
  })

  it('shows a field that went from empty to a value as Not provided then the value', () => {
    renderDiff({ title: 'T', notes: 'n', impact: null, owner: 'Sam', last_approved: { title: 'T', notes: 'n', impact: null } })
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows).toHaveLength(1)
    expect(within(rows[0]).getByText('Not provided')).toBeInTheDocument()
    expect(within(rows[0]).getByText('Sam')).toBeInTheDocument()
  })

  it('renders hostile text literally', () => {
    renderDiff({ title: 'a‮b', last_approved: { title: 'a' } })
    expect(screen.getByText('a\\u202eb')).toBeInTheDocument()
  })
})
