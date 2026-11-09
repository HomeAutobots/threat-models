import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../api/queries'
import { Home } from './Home'

describe('Home', () => {
  it('escapes the systems load error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        url.endsWith('/systems')
          ? new Response(JSON.stringify({ detail: 'bad‮gnp' }), { status: 422, headers: { 'Content-Type': 'application/json' } })
          : new Response(JSON.stringify({}), { status: 200, headers: { 'Content-Type': 'application/json' } }),
      ),
    )
    render(
      <MantineProvider>
        <QueryClientProvider client={makeQueryClient()}>
          <MemoryRouter>
            <Home reg="main" />
          </MemoryRouter>
        </QueryClientProvider>
      </MantineProvider>,
    )
    expect(await screen.findByText('Could not load systems: bad\\u202egnp')).toBeInTheDocument()
  })
})
