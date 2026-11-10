import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../api/queries'
import type { Risk } from '../api/types'
import { RiskPage } from './RiskPage'

const meta = {
  fields: [],
  editable: ['title'],
  statuses: ['open', 'mitigated'],
  labels: { title: 'Title' },
  stride: {},
  linddun: [],
  note_min: 20,
}

let risk: Risk

function renderPage(reg = 'main', metaFails = false) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const body =
        url === '/api/meta'
          ? metaFails
            ? undefined
            : meta
          : url.endsWith('/history')
            ? []
            : {
                risk,
                elements: {},
                model: { state: 'current', latest_id: 'MODEL-1', written_against: 'MODEL-1', moved_on: false, changed: [], basis: 'model' },
                editors_since_approval: [],
                duplicate: null,
              }
      if (body === undefined) return new Response(JSON.stringify({ detail: 'meta is down' }), { status: 422, headers: { 'Content-Type': 'application/json' } })
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }),
  )
  render(
    <MantineProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <MemoryRouter initialEntries={[`/${reg}/demo/risks/T-1`]}>
          <Routes>
            <Route path="/:reg/:slug/risks/:id" element={<RiskPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  )
}

const mk = (over: Partial<Risk>) =>
  ({ id: 'T-1', title: 'A title', review_state: 'approved', status: 'open', elements: [], last_approved: null, ...over }) as Risk

const RETIRED_TEXT = 'Retired risks are read-only. To bring one back, add it as a new risk.'

beforeEach(() => {
  risk = mk({})
})

describe('RiskPage', () => {
  it('approved: Edit, Change status and Retire', async () => {
    renderPage()
    expect(await screen.findByRole('link', { name: 'Edit' })).toHaveAttribute('href', '/main/demo/risks/T-1/edit')
    expect(screen.getByRole('button', { name: 'Change status' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retire' })).toBeInTheDocument()
  })

  it('renders no nested main landmark, and one h1 with the ID and title', async () => {
    renderPage()
    expect(await screen.findByRole('link', { name: 'Edit' })).toBeInTheDocument()
    expect(document.querySelector('main')).toBeNull()
    const h1s = screen.getAllByRole('heading', { level: 1 })
    expect(h1s).toHaveLength(1)
    expect(h1s[0]).toHaveTextContent('T-1A title')
  })

  it('retired: none of Edit, Change status, Retire, and the read-only line', async () => {
    risk = mk({ status: 'retired' })
    renderPage()
    expect(await screen.findByText(RETIRED_TEXT)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Change status' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retire' })).not.toBeInTheDocument()
  })

  it('rejected: read-only line, no actions', async () => {
    risk = mk({ review_state: 'rejected' })
    renderPage()
    expect(await screen.findByText('Rejected risks are read-only.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retire' })).not.toBeInTheDocument()
  })

  it('pending: Edit, Change status, a review link, no Retire', async () => {
    risk = mk({ review_state: 'pending' })
    renderPage()
    expect(await screen.findByRole('link', { name: 'Review this risk' })).toHaveAttribute(
      'href',
      '/main/demo/review?id=T-1',
    )
    expect(screen.getByRole('link', { name: 'Edit' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change status' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retire' })).not.toBeInTheDocument()
  })

  it('shows a Trial register badge on the action panel in trial only', async () => {
    renderPage('trial')
    expect(await screen.findByText('Trial register')).toBeInTheDocument()
  })

  it('has no trial badge in main', async () => {
    renderPage()
    await screen.findByRole('link', { name: 'Edit' })
    expect(screen.queryByText('Trial register')).not.toBeInTheDocument()
  })

  it('shows an alert when the metadata fails to load', async () => {
    renderPage('main', true)
    expect(await screen.findByRole('alert')).toHaveTextContent(/meta is down/)
  })

  it('Change status and Retire open their modals', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Change status' }))
    expect(await screen.findByRole('button', { name: 'Save status' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    fireEvent.click(screen.getByRole('button', { name: 'Retire' }))
    expect(await screen.findByLabelText('Reason')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retire T-1' })).toBeDisabled()
  })
})
