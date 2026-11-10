import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../api/queries'
import type { C4Response, Risk } from '../api/types'
import { c4, item } from '../test-c4'
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
let model: C4Response | null = null

function Where() {
  const loc = useLocation()
  return <div data-testid="where">{loc.pathname + loc.search}</div>
}

function renderPage(metaFails = false, metaDetail = 'meta is down') {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      url === '/api/meta' && metaFails
        ? new Response(JSON.stringify({ detail: metaDetail }), { status: 422, headers: { 'Content-Type': 'application/json' } })
        : url.endsWith('/c4') && !model
          ? new Response(JSON.stringify({ detail: 'no model' }), { status: 404, headers: { 'Content-Type': 'application/json' } })
          : new Response(JSON.stringify(url === '/api/meta' ? meta : url.endsWith('/risks') ? risks : url.endsWith('/c4') ? model : {}), {
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
  model = null
  risks = [
    mk('A-1'),
    mk('A-2', { title: 'Needle in a haystack', elements: ['E2'], status: 'planned' }),
    mk('P-1', { review_state: 'pending' }),
    mk('R-1', { review_state: 'rejected' }),
    mk('X-1', { status: 'retired' }),
  ]
})

describe('RegisterPage', () => {
  it('every tab points aria-controls at a real panel', async () => {
    renderPage()
    const tabs = await screen.findAllByRole('tab')
    expect(tabs).toHaveLength(4)
    for (const t of tabs) {
      const panel = document.getElementById(t.getAttribute('aria-controls') ?? '')
      expect(panel).not.toBeNull()
      expect(panel).toHaveAttribute('role', 'tabpanel')
    }
  })

  it('shows an alert when the metadata fails to load', async () => {
    renderPage(true)
    expect(await screen.findByRole('alert')).toHaveTextContent(/meta is down/)
  })

  it('escapes control and bidi characters in a metadata error', async () => {
    renderPage(true, 'meta \u202e down')
    expect(await screen.findByRole('alert')).toHaveTextContent('meta \\u202e down')
  })

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

  it('has the row ID as a link to the risk page, for keyboard users', async () => {
    renderPage()
    await screen.findByText('Title of A-1')
    expect(screen.getByRole('link', { name: 'A-1' })).toHaveAttribute('href', '/main/demo/risks/A-1')
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

  describe('Include what is inside', () => {
    const tree = () =>
      c4({
        latest_record: {
          items: {
            S1: item({ kind: 'softwareSystem', name: 'Shop', where: ['S1'] }),
            C2: item({ name: 'Orders API', parent: 'S1', where: ['S1', 'C2'] }),
            K1: item({ kind: 'component', name: 'Cart', parent: 'C2', where: ['S1', 'C2', 'K1'] }),
            C3: item({ name: 'Other', parent: 'S1', where: ['S1', 'C3'] }),
          },
          rels: {},
          views: {},
        },
      })

    beforeEach(() => {
      model = tree()
      risks = [
        mk('A-1', { elements: ['C2'] }),
        mk('A-2', { title: 'Inside', elements: ['K1'] }),
        mk('A-3', { title: 'Sibling', elements: ['C3'] }),
      ]
    })

    it('the element filter alone matches the chosen ID only', async () => {
      renderPage()
      await screen.findByLabelText("Include what's inside")
      fireEvent.change(screen.getByLabelText('Element'), { target: { value: 'C2' } })
      expect(screen.getByText('Title of A-1')).toBeInTheDocument()
      expect(screen.queryByText('Inside')).not.toBeInTheDocument()
    })

    it('the checkbox adds the items inside the chosen one', async () => {
      renderPage()
      fireEvent.change(await screen.findByLabelText('Element'), { target: { value: 'C2' } })
      fireEvent.click(await screen.findByLabelText("Include what's inside"))
      expect(screen.getByText('Title of A-1')).toBeInTheDocument()
      expect(screen.getByText('Inside')).toBeInTheDocument()
      expect(screen.queryByText('Sibling')).not.toBeInTheDocument()
    })

    it('without an approved model the checkbox is hidden and the filter still works', async () => {
      model = null
      renderPage()
      fireEvent.change(await screen.findByLabelText('Element'), { target: { value: 'C2' } })
      expect(screen.getByText('Title of A-1')).toBeInTheDocument()
      expect(screen.queryByLabelText("Include what's inside")).not.toBeInTheDocument()
    })

    it('a model with no approval hides the checkbox too', async () => {
      model = c4({ latest_record: null })
      renderPage()
      await screen.findByLabelText('Element')
      expect(screen.queryByLabelText("Include what's inside")).not.toBeInTheDocument()
    })
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
