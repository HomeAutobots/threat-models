import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../../api/queries'
import { RECORD } from '../../test-c4'
import { RoutesPanel, endpointOptions } from './RoutesPanel'

describe('RoutesPanel', () => {
  it('offers only people, systems, containers and components, labelled ID Name', () => {
    expect(endpointOptions(RECORD).map((o) => o.label)).toEqual(['A1 Customer', 'S1 Shop', 'C1 Web app', 'C2 Orders API', 'K1 Cart'])
  })

  it('asks for no route until both ends are chosen', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(
      <MantineProvider>
        <QueryClientProvider client={makeQueryClient()}>
          <RoutesPanel reg="main" slug="demo" record={RECORD} />
        </QueryClientProvider>
      </MantineProvider>,
    )
    expect(screen.getAllByLabelText('From').length).toBeGreaterThan(0)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
