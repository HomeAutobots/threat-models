import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../api/queries'
import type { Reg } from '../api/types'
import { AppShell } from './AppShell'

const BANNER = 'Trial register: practice data, not the real register'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function mockApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url === '/api/session') return json({ reviewer: 'Sam Reviewer', trial: true })
      if (url.endsWith('/systems')) return json([{ slug: 'demo', name: 'Demo', created_at: 'x' }])
      if (url.endsWith('/risks') || url.includes('/risks?')) {
        return json([{ id: 'T1', review_state: 'pending' }, { id: 'T2', review_state: 'approved' }])
      }
      return json({}, 404)
    }),
  )
}

function renderShell(reg: Reg) {
  return render(
    <MantineProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <MemoryRouter initialEntries={[`/${reg}/demo/register`]}>
          <AppShell reg={reg} slug="demo">
            <p>page body</p>
          </AppShell>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  )
}

describe('AppShell', () => {
  beforeEach(mockApi)

  it('shows the trial banner for the trial register', async () => {
    renderShell('trial')
    expect(await screen.findByText(BANNER)).toBeInTheDocument()
    expect(await screen.findByText('Signed in as Sam Reviewer')).toBeInTheDocument()
  })

  it('has no banner for the main register, and shows the pending count', async () => {
    renderShell('main')
    expect(await screen.findByText('Signed in as Sam Reviewer')).toBeInTheDocument()
    expect(await screen.findByText('1')).toBeInTheDocument()
    expect(screen.queryByText(BANNER)).not.toBeInTheDocument()
    expect(screen.getByText('Threat models')).toBeInTheDocument()
    expect(screen.getByText('page body')).toBeInTheDocument()
  })
})
