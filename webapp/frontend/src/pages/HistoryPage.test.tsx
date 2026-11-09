import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../api/queries'
import { HistoryPage } from './HistoryPage'

let problems: string[]

function json(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  problems = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.endsWith('/verify')) return json({ problems })
      if (url.endsWith('/history'))
        return json([
          { seq: 1, at: '2026-01-02T03:04:00Z', op: 'update', tbl: 'risks', row_key: 'T-1', actor: 'ai:run-7', diff: {}, note: 'hello', prev_hash: '', hash: 'h' },
        ])
      return json({})
    }),
  )
})

function renderPage() {
  render(
    <MantineProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <MemoryRouter initialEntries={['/main/demo/history']}>
          <Routes>
            <Route path="/:reg/:slug/history" element={<HistoryPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  )
}

describe('HistoryPage', () => {
  it('shows the ok line and the rows', async () => {
    renderPage()
    expect(await screen.findByText('Change log verified: the hash chain and stored rows match.')).toBeInTheDocument()
    expect(screen.getByText('AI, run run-7')).toBeInTheDocument()
    expect(screen.getByText('risks / T-1')).toBeInTheDocument()
    expect(screen.getByText('hello')).toBeInTheDocument()
  })

  it('lists problems, escaped', async () => {
    problems = ['chain broken at 3', 'bad\u001brow']
    renderPage()
    expect(await screen.findByText('chain broken at 3')).toBeInTheDocument()
    expect(screen.getByText('bad\\x1brow')).toBeInTheDocument()
    expect(screen.queryByText(/Change log verified/)).toBeNull()
  })
})
