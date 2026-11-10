import { MantineProvider } from '@mantine/core'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RECORD } from '../../test-c4'
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
})
