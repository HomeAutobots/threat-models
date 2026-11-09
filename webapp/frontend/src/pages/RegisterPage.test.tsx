import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../api/queries'
import type { Risk } from '../api/types'
import { RegisterPage } from './RegisterPage'

const meta = { stride: { S: 'Spoofing' }, linddun: [], statuses: ['open', 'retired'], origins: ['ai', 'human'] }

function mk(id: string, over: Partial<Risk> = {}): Risk {
  return {
    id,
    title: `Title of ${id}`,
    review_state: 'approved',
    status: 'open',
    last_approved: null,
    elements: ['E1'],
    category: 'S',
    origin: 'ai',
    drafted_by: 'ai:run-1',
    updated_at: '2026-01-02T03:04:05Z',
    ...over,
  } as Risk
}

let risks: Risk[]

function Where() {
  const loc = useLocation()
  return <div data-testid="where">{loc.pathname + loc.search}</div>
}

function renderPage() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      new Response(JSON.stringify(url === '/api/meta' ? meta : url.endsWith('/risks') ? risks : {}), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
  render(
    <MantineProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <MemoryRouter initialEntries={['/main/demo/register']}>
          <Routes>
            <Route path="/:reg/:slug/register" element={<RegisterPage />} />
            <Route path="*" element={<Where />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  )
}

beforeEach(() => {
  risks = [
    mk('A-1'),
    mk('A-2', { title: 'Needle in a haystack', elements: ['E2'], status: 'planned' }),
    mk('P-1', { review_state: 'pending' }),
    mk('R-1', { review_state: 'rejected' }),
    mk('X-1', { status: 'retired' }),
  ]
})

describe('RegisterPage', () => {
  it('counts the tabs, and a retired risk is only under Retired', async () => {
    renderPage()
    expect(await screen.findByRole('tab', { name: /Approved/ })).toHaveTextContent('Approved2')
    expect(screen.getByRole('tab', { name: /Pending review/ })).toHaveTextContent('Pending review1')
    expect(screen.getByRole('tab', { name: /Rejected/ })).toHaveTextContent('Rejected1')
    expect(screen.getByRole('tab', { name: /Retired/ })).toHaveTextContent('Retired1')
    expect(screen.queryByText('Title of X-1')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /Retired/ }))
    expect(await screen.findByText('Title of X-1')).toBeInTheDocument()
  })

  it('text search is case-insensitive over ID and title', async () => {
    renderPage()
    await screen.findByText('Title of A-1')
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'NEEDLE' } })
    expect(screen.getByText('Needle in a haystack')).toBeInTheDocument()
    expect(screen.queryByText('Title of A-1')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'a-1' } })
    expect(screen.getByText('Title of A-1')).toBeInTheDocument()
  })

  it('filters by element and status', async () => {
    renderPage()
    await screen.findByText('Title of A-1')
    fireEvent.change(screen.getByLabelText('Element'), { target: { value: 'E2' } })
    expect(screen.queryByText('Title of A-1')).not.toBeInTheDocument()
    expect(screen.getByText('Needle in a haystack')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Element'), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'open' } })
    expect(screen.queryByText('Needle in a haystack')).not.toBeInTheDocument()
  })

  it('shows the AI-changed banner, singular and plural', async () => {
    risks = [mk('P-1', { review_state: 'pending', last_approved: { title: 'x' } })]
    renderPage()
    const banner = await screen.findByText('1 approved risk was changed by AI and needs your review')
    expect(within(banner.parentElement as HTMLElement).getByRole('link', { name: 'Review now' })).toHaveAttribute(
      'href',
      '/main/demo/review',
    )
  })

  it('banner is plural for two, and absent for a new pending risk', async () => {
    risks = [
      mk('P-1', { review_state: 'pending', last_approved: { a: 1 } }),
      mk('P-2', { review_state: 'pending', last_approved: { a: 1 } }),
      mk('P-3', { review_state: 'pending' }),
    ]
    renderPage()
    expect(await screen.findByText('2 approved risks were changed by AI and need your review')).toBeInTheDocument()
  })

  it('no banner without AI changes', async () => {
    renderPage()
    await screen.findByText('Title of A-1')
    expect(screen.queryByText(/changed by AI/)).not.toBeInTheDocument()
  })

  it('a Pending-tab row opens the review queue at that risk', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('tab', { name: /Pending review/ }))
    fireEvent.click(await screen.findByText('Title of P-1'))
    expect(screen.getByTestId('where').textContent).toBe('/main/demo/review?id=P-1')
  })

  it('an Approved-tab row opens the risk page, and the buttons link out', async () => {
    renderPage()
    fireEvent.click(await screen.findByText('Title of A-1'))
    expect(screen.getByTestId('where').textContent).toBe('/main/demo/risks/A-1')
  })

  it('has Add risk and Report links', async () => {
    renderPage()
    expect(await screen.findByRole('link', { name: 'Add risk' })).toHaveAttribute('href', '/main/demo/risks/new')
    expect(screen.getByRole('link', { name: 'Report' })).toHaveAttribute('href', '/main/demo/reports')
  })
})
