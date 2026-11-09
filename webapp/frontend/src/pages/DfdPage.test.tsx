import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../api/queries'
import type { DfdResponse } from '../api/types'
import { DfdPage } from './DfdPage'

vi.mock('mermaid', () => ({ default: { initialize: vi.fn(), render: vi.fn(async () => ({ svg: '<svg></svg>' })) } }))

const NOTE = 'This is a careful approval.'
const BANNER = /This file contains content the readable view doesn't show/
const STALE = 'dfd.md changed since it was shown. Review the current file.'

let dfd: DfdResponse
let posts: { url: string; body: { note: string; expected_sha256: string } }[]
let postReply: () => Response
let gets: number
let getGate: Promise<void> | null

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function mk(text: string | null, over: Partial<DfdResponse> = {}): DfdResponse {
  return {
    status: { state: 'changed', latest: null, current_sha256: 'cur' },
    approvals: [
      { id: 'DFD-1', version: '1', sha256: 'a', ids: [], approved_by: 'human:ann', approved_at: '2026-01-02T03:04:00Z', note: 'first one' },
    ],
    preview: { version: '2', sha256: 'sha-seen', ids: { E: ['E1'] }, details: {}, added: ['E2'], removed: ['E9'], warnings: ['careful'] },
    preview_error: null,
    text,
    ...over,
  }
}

beforeEach(() => {
  posts = []
  gets = 0
  getGate = null
  postReply = () => json({ approval: {} })
  dfd = mk('# Title\n\nclean text')
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        posts.push({ url, body: JSON.parse(String(init.body)) })
        return postReply()
      }
      if (url === '/api/meta') return json({ note_min: 20 })
      if (url.endsWith('/dfd')) {
        gets++
        if (getGate && gets > 1) await getGate
        return json(dfd)
      }
      return json({}, 404)
    }),
  )
})

function renderPage() {
  render(
    <MantineProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <MemoryRouter initialEntries={['/main/demo/dfd']}>
          <Routes>
            <Route path="/:reg/:slug/dfd" element={<DfdPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  )
}

async function typeNote(v = NOTE) {
  const box = await screen.findByLabelText('Approval note')
  fireEvent.change(box, { target: { value: v } })
}

describe('DfdPage', () => {
  it('shows status, approvals, and preview', async () => {
    renderPage()
    expect(await screen.findByText('changed')).toBeInTheDocument()
    expect(screen.getByText('DFD-1')).toBeInTheDocument()
    expect(screen.getByText('first one')).toBeInTheDocument()
    expect(screen.getByText('E2')).toBeInTheDocument()
    expect(screen.getByText('E9')).toBeInTheDocument()
    expect(screen.getByText('careful')).toBeInTheDocument()
  })

  it('shows the hidden-content banner for an HTML comment, not for clean text', async () => {
    dfd = mk('hello <!-- x --> there')
    renderPage()
    expect(await screen.findByText(BANNER)).toBeInTheDocument()
  })

  it('no banner for clean text', async () => {
    renderPage()
    await screen.findByText('clean text')
    expect(screen.queryByText(BANNER)).toBeNull()
  })

  it('banner for raw HTML links to the Exact file tab', async () => {
    dfd = mk('<b>x</b>')
    renderPage()
    await screen.findByText(BANNER)
    fireEvent.click(screen.getByRole('button', { name: 'Exact file view' }))
    expect(screen.getByRole('tab', { name: 'Exact file' })).toHaveAttribute('aria-selected', 'true')
  })

  it('raw HTML in the text does not render as HTML', async () => {
    dfd = mk('text <img src=x onerror=alert(1)> more')
    renderPage()
    await screen.findByText(BANNER)
    expect(document.querySelector('img')).toBeNull()
  })

  it('a remote markdown image renders no img, only a placeholder', async () => {
    dfd = mk('before ![logo\u001b](https://attacker.example/p.png?leak) after')
    renderPage()
    expect(await screen.findByText('Image not loaded: logo\\x1b')).toBeInTheDocument()
    expect(document.querySelector('img')).toBeNull()
  })

  it('the Exact view shows control characters escaped', async () => {
    dfd = mk('a\u001bb')
    renderPage()
    fireEvent.click(await screen.findByRole('tab', { name: 'Exact file' }))
    expect(await screen.findByText('a\\x1bb')).toBeInTheDocument()
  })

  it('Approve DFD stays disabled until the note is long enough, then posts expected_sha256', async () => {
    renderPage()
    const btn = await screen.findByRole('button', { name: 'Approve DFD' })
    expect(btn).toBeDisabled()
    await typeNote('short')
    expect(btn).toBeDisabled()
    await typeNote()
    expect(btn).toBeEnabled()
    fireEvent.click(btn)
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].url).toMatch(/\/dfd\/approve$/)
    expect(posts[0].body).toEqual({ note: NOTE, expected_sha256: 'sha-seen' })
  })

  it('is disabled when the status is current or there is a preview_error', async () => {
    dfd = mk('x', { status: { state: 'current', latest: null, current_sha256: 'cur' } })
    renderPage()
    await typeNote()
    expect(await screen.findByRole('button', { name: 'Approve DFD' })).toBeDisabled()
  })

  it('is disabled with a preview_error, which is shown', async () => {
    dfd = mk('x', { preview: null, preview_error: 'bad\u001bfile' })
    renderPage()
    await typeNote()
    expect(await screen.findByText('bad\\x1bfile')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve DFD' })).toBeDisabled()
  })

  it('on 409 shows the stale text, refetches, keeps Approve disabled while refetching, never retries', async () => {
    renderPage()
    await typeNote()
    let release: () => void = () => {}
    getGate = new Promise<void>((r) => (release = r))
    postReply = () => json({ detail: 'x', current_sha256: 'new' }, 409)
    fireEvent.click(await screen.findByRole('button', { name: 'Approve DFD' }))
    expect(await screen.findByText(STALE)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve DFD' })).toBeDisabled()
    dfd = mk('# new', { preview: { ...dfd.preview!, sha256: 'sha-new' } })
    release()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Approve DFD' })).toBeEnabled())
    expect(posts).toHaveLength(1)
  })

  it('shows a 422 detail escaped', async () => {
    renderPage()
    await typeNote()
    postReply = () => json({ detail: 'nope\u001b' }, 422)
    fireEvent.click(await screen.findByRole('button', { name: 'Approve DFD' }))
    expect(await screen.findByText('nope\\x1b')).toBeInTheDocument()
  })
})
