import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../api/queries'
import type { Risk } from '../api/types'
import { RiskPage } from './RiskPage'

const meta = {
  fields: [],
  editable: ['title'],
  labels: { title: 'Title' },
  stride: {},
  linddun: [],
  note_min: 20,
}

let risk: Risk

function renderPage() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const body =
        url === '/api/meta'
          ? meta
          : url.endsWith('/history')
            ? []
            : {
                risk,
                elements: {},
                dfd: { state: 'current', latest_id: 'D', written_against: 'D', error: null },
                editors_since_approval: [],
                duplicate: null,
              }
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }),
  )
  render(
    <MantineProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <MemoryRouter initialEntries={['/main/demo/risks/T-1']}>
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
})
