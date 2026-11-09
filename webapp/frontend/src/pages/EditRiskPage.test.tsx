import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../api/queries'
import type { Risk } from '../api/types'
import { EditRiskPage } from './EditRiskPage'

const STALE = 'This risk changed after you opened it. Review the current version.'

const meta = {
  fields: [],
  editable: [
    'title',
    'elements',
    'category',
    'origin',
    'method',
    'description',
    'control_refs',
    'notes',
    'treatment',
    'ai_confidence',
    'status',
  ],
  labels: {},
  stride: { S: 'Spoofing', T: 'Tampering' },
  linddun: ['Linking'],
  statuses: ['open', 'mitigated'],
  treatments: ['mitigate', 'accept'],
  confidence: ['high', 'low'],
  methods: ['interview', 'stride'],
  origins: ['ai-draft', 'owner'],
  human_required: ['title', 'elements', 'category', 'origin', 'description'],
  note_min: 20,
}

function mk(over: Partial<Risk> = {}): Risk {
  return {
    id: 'T-1',
    title: 'Original title',
    elements: ['web'],
    category: 'S',
    origin: 'owner',
    method: null,
    description: 'Original description',
    control_refs: ['C-1'],
    notes: 'Original notes',
    treatment: null,
    ai_confidence: null,
    status: 'open',
    review_state: 'approved',
    last_approved: null,
    ...over,
  } as Risk
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

let stored: Risk
let posts: { url: string; body: any }[]
let reply: (url: string) => Response

function Where() {
  const loc = useLocation()
  return <div data-testid="where">{loc.pathname + loc.search}</div>
}

function renderPage(mode: 'add' | 'edit', initial: string) {
  render(
    <MantineProvider env="test">
      <QueryClientProvider client={makeQueryClient()}>
        <MemoryRouter initialEntries={[initial]}>
          <Routes>
            <Route path="/:reg/:slug/risks/new" element={<EditRiskPage mode="add" />} />
            <Route path="/:reg/:slug/risks/:id/edit" element={<EditRiskPage mode={mode} />} />
            <Route path="*" element={<Where />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  )
}

beforeEach(() => {
  stored = mk()
  posts = []
  reply = () => json({ risk: stored })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        posts.push({ url, body: JSON.parse(String(init.body)) })
        return reply(url)
      }
      if (url === '/api/meta') return json(meta)
      if (url.endsWith('/history')) return json([])
      return json({
        risk: stored,
        elements: {},
        dfd: { state: 'current', latest_id: null, written_against: null, error: null },
        editors_since_approval: [],
        duplicate: null,
      })
    }),
  )
})

describe('EditRiskPage', () => {
  it('edit posts only the changed fields, with seen and reason; cleared list is []', async () => {
    renderPage('edit', '/main/demo/risks/T-1/edit')
    const title = await screen.findByLabelText('Title')
    fireEvent.change(title, { target: { value: 'New title' } })
    fireEvent.change(screen.getByLabelText('Notes'), { target: { value: '' } })
    fireEvent.keyDown(await screen.findByRole('combobox', { name: /^Control references/ }), { key: 'Backspace' })
    fireEvent.change(screen.getByLabelText('Reason for change (optional)'), { target: { value: 'tidy' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].url).toBe('/api/main/systems/demo/risks/T-1/edit')
    expect(posts[0].body).toEqual({
      fields: { title: 'New title', notes: '', control_refs: [] },
      seen: stored,
      reason: 'tidy',
    })
  })

  it('saving an approved risk goes to the risk page', async () => {
    renderPage('edit', '/main/demo/risks/T-1/edit')
    fireEvent.change(await screen.findByLabelText('Title'), { target: { value: 'X' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect((await screen.findByTestId('where')).textContent).toBe('/main/demo/risks/T-1')
  })

  it('pending goes to review?id=', async () => {
    stored = mk({ review_state: 'pending' })
    renderPage('edit', '/main/demo/risks/T-1/edit?return=review')
    fireEvent.change(await screen.findByLabelText('Title'), { target: { value: 'X' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect((await screen.findByTestId('where')).textContent).toBe('/main/demo/review?id=T-1')
  })

  it('Cancel on an edit goes to the risk page', async () => {
    renderPage('edit', '/main/demo/risks/T-1/edit')
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
    expect((await screen.findByTestId('where')).textContent).toBe('/main/demo/risks/T-1')
  })

  it('Cancel with ?return=review goes back to that review', async () => {
    renderPage('edit', '/main/demo/risks/T-1/edit?return=review')
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
    expect((await screen.findByTestId('where')).textContent).toBe('/main/demo/review?id=T-1')
  })

  it('Cancel on add goes to the register', async () => {
    renderPage('add', '/main/demo/risks/new')
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
    expect((await screen.findByTestId('where')).textContent).toBe('/main/demo/register')
  })

  it('add marks the human-required fields required and posts fields, then opens review', async () => {
    reply = () => json({ risk: mk({ id: 'T-9', review_state: 'pending' }) })
    renderPage('add', '/main/demo/risks/new')
    for (const label of ['Title', 'Elements', 'Category', 'Origin', 'Description']) {
      const el = await screen.findByRole(label === 'Elements' ? 'combobox' : label === 'Category' || label === 'Origin' ? 'combobox' : 'textbox', { name: new RegExp(`^${label}`) })
      expect(el.id).toBeTruthy()
      expect(document.querySelector(`label[for="${el.id}"]`)?.textContent).toContain('*')
    }
    const notes = screen.getByLabelText(/^Notes/)
    expect(document.querySelector(`label[for="${notes.id}"]`)?.textContent).not.toContain('*')
    fireEvent.change(screen.getByLabelText(/^Title/), { target: { value: 'Brand new' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].url).toBe('/api/main/systems/demo/risks')
    expect(posts[0].body).toEqual({ fields: { title: 'Brand new' } })
    expect((await screen.findByTestId('where')).textContent).toBe('/main/demo/review?id=T-9')
  })

  it('a 409 shows the stale banner, takes the current record and keeps the typed values', async () => {
    const current = mk({ title: 'Changed by someone', notes: 'Their notes' })
    reply = () => json({ detail: 'stale', current }, 409)
    renderPage('edit', '/main/demo/risks/T-1/edit')
    fireEvent.change(await screen.findByLabelText('Title'), { target: { value: 'Mine' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText(STALE)).toBeInTheDocument()
    expect((screen.getByLabelText('Title') as HTMLTextAreaElement).value).toBe('Mine')
    // Untouched fields take the current value, so a second save cannot undo the other change.
    expect((screen.getByLabelText('Notes') as HTMLTextAreaElement).value).toBe('Their notes')
    reply = () => json({ risk: current })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(posts).toHaveLength(2))
    expect(posts[1].body).toEqual({ fields: { title: 'Mine' }, seen: current, reason: '' })
  })

  it('a 422 shows the escaped detail above Save', async () => {
    reply = () => json({ detail: 'bad‮gnp' }, 422)
    renderPage('edit', '/main/demo/risks/T-1/edit')
    fireEvent.change(await screen.findByLabelText('Title'), { target: { value: 'X' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('bad\\u202egnp')).toBeInTheDocument()
  })

  it('a double click on Save posts once', async () => {
    renderPage('edit', '/main/demo/risks/T-1/edit')
    fireEvent.change(await screen.findByLabelText('Title'), { target: { value: 'X' } })
    const save = screen.getByRole('button', { name: 'Save' })
    fireEvent.click(save)
    fireEvent.click(save)
    await waitFor(() => expect(posts).toHaveLength(1))
  })

  it('refuses to edit a retired risk', async () => {
    stored = mk({ status: 'retired' })
    renderPage('edit', '/main/demo/risks/T-1/edit')
    expect(await screen.findByText(/can't be edited/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
  })

  it('category offers STRIDE letters with names and LINDDUN names', async () => {
    renderPage('edit', '/main/demo/risks/T-1/edit')
    await userEvent.setup().click(await screen.findByRole('combobox', { name: /^Category/ }))
    expect(await screen.findByRole('option', { name: 'S - Spoofing' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'T - Tampering' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Linking' })).toBeInTheDocument()
  })
})
