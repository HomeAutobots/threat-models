import { MantineProvider } from '@mantine/core'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RECORD, realC4 } from '../../test-c4'
import { ItemTables } from './ItemTables'

describe('ItemTables', () => {
  it('selects a row by its ID and lists TB contents and crossing paths', () => {
    const onSelect = vi.fn()
    render(
      <MantineProvider>
        <ItemTables record={RECORD} counts={{}} selected={null} onSelect={onSelect} />
      </MantineProvider>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Select K1' }))
    expect(onSelect).toHaveBeenCalledWith('K1')
    expect(screen.getByRole('table', { name: 'Trust boundaries' })).toHaveTextContent('R1')
  })

  it('renders no sections for an empty model', () => {
    render(
      <MantineProvider>
        <ItemTables record={{ items: {}, rels: {}, views: {} }} counts={{}} selected={null} onSelect={() => {}} />
      </MantineProvider>,
    )
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('lists what is inside a trust boundary from the zones, per environment (R39e)', () => {
    const record = realC4('changed').preview!.record
    render(
      <MantineProvider>
        <ItemTables record={record} counts={{}} selected={null} onSelect={() => {}} />
      </MantineProvider>,
    )
    const tb = screen.getByRole('table', { name: 'Trust boundaries' })
    const rows = Object.fromEntries(
      [...tb.querySelectorAll('tbody tr')].map((tr) => [tr.querySelector('td')!.textContent, tr.textContent]),
    )
    expect(rows.TB2).toContain('ENV1: C2, C3')
    expect(rows.TB1).toContain('ENV1: A1, C1, N1')
    expect(rows.TB2).toContain('ENV1: R2')
    expect(rows.TB1).toContain('ENV1: R2')
  })

  it('orders rows by kind (A, S, C, K, R, TB, N, I) then number', () => {
    const rec = {
      items: {
        S1: RECORD.items.A1,
        A2: { ...RECORD.items.A1, name: 'Second' },
        C10: { ...RECORD.items.C2, name: 'Ten' },
        C2: RECORD.items.C2,
      },
      rels: {},
      views: {},
    }
    render(
      <MantineProvider>
        <ItemTables record={rec} counts={{}} selected={null} onSelect={() => {}} />
      </MantineProvider>,
    )
    const ids = (name: string) => [...screen.getByRole('table', { name }).querySelectorAll('tbody tr')].map((tr) => tr.querySelector('td')!.textContent)
    expect(ids('People and systems')).toEqual(['A2', 'S1'])
    expect(ids('Containers')).toEqual(['C2', 'C10'])
  })
})

