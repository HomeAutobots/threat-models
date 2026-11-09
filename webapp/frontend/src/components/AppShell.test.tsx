import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useNavigate } from 'react-router'
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

function GoTo({ to }: { to: string }) {
  const navigate = useNavigate()
  return <button onClick={() => navigate(to)}>go {to}</button>
}

function renderShell(reg: Reg) {
  return render(
    <MantineProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <MemoryRouter initialEntries={[`/${reg}/demo/register`]}>
          <AppShell reg={reg} slug="demo">
            <p>page body</p>
            <GoTo to="/main/demo/review?id=T-2" />
            <GoTo to="/main/demo/register#x" />
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

  it('has a labeled Burger that opens the navbar below the breakpoint, and choosing a page closes it', async () => {
    const user = userEvent.setup()
    renderShell('main')
    const burger = screen.getByRole('button', { name: 'Toggle navigation' })
    const navbar = document.getElementById(burger.getAttribute('aria-controls') ?? '')
    expect(navbar).toHaveAttribute('aria-label', 'Pages')
    expect(burger).toHaveAttribute('aria-expanded', 'false')
    expect(navbar).toHaveAttribute('data-collapsed', 'true')

    await user.click(burger)
    expect(burger).toHaveAttribute('aria-expanded', 'true')
    expect(navbar).not.toHaveAttribute('data-collapsed')

    await user.click(screen.getByRole('link', { name: /Review queue/ }))
    expect(burger).toHaveAttribute('aria-expanded', 'false')
    expect(navbar).toHaveAttribute('data-collapsed', 'true')
  })

  it('closes the navbar on any location change, not only a nav-link click', async () => {
    const user = userEvent.setup()
    renderShell('main')
    const burger = screen.getByRole('button', { name: 'Toggle navigation' })
    await user.click(burger)
    expect(burger).toHaveAttribute('aria-expanded', 'true')
    await user.click(screen.getByRole('button', { name: 'go /main/demo/review?id=T-2' }))
    expect(burger).toHaveAttribute('aria-expanded', 'false')
  })

  it('renders one main landmark and leaves the page its own h1', async () => {
    renderShell('main')
    expect(await screen.findByText('Signed in as Sam Reviewer')).toBeInTheDocument()
    expect(document.querySelectorAll('main')).toHaveLength(1)
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument()
  })
})
