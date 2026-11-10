import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../api/queries'
import type { C4Response } from '../api/types'
import { RECORD, c4, risk } from '../test-c4'
import { ArchitecturePage } from './ArchitecturePage'

const NOTE = 'This is a careful approval.'

let model: C4Response
let posts: { url: string; body: Record<string, string> }[]
let postReply: (url: string) => Response
let gets: number
let getGate: Promise<void> | null
let routesReply: () => Response

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  posts = []
  gets = 0
  getGate = null
  postReply = () => json({ approval: {} })
  routesReply = () => json({ chains: [] })
  model = c4()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        posts.push({ url, body: JSON.parse(String(init.body)) })
        return postReply(url)
      }
      if (url === '/api/meta') return json({ note_min: 20 })
      if (url.endsWith('/c4')) {
        gets++
        if (getGate && gets > 1) await getGate
        return json(model)
      }
      if (url.includes('/c4/routes')) return routesReply()
      if (url.endsWith('/risks')) return json([risk('RISK-1', ['C2']), risk('RISK-2', ['R1']), risk('RISK-3', ['K1'], { review_state: 'rejected' })])
      return json({}, 404)
    }),
  )
})

function renderPage() {
  render(
    <MantineProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <MemoryRouter initialEntries={['/main/demo/architecture']}>
          <Routes>
            <Route path="/:reg/:slug/architecture" element={<ArchitecturePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  )
}

async function typeNote(v = NOTE) {
  fireEvent.change(await screen.findByLabelText('Approval note'), { target: { value: v } })
}

async function pick(label: string, value: string) {
  const input = screen.getAllByLabelText(label).find((e) => e.tagName === 'INPUT')!
  fireEvent.click(input)
  const list = document.getElementById(input.getAttribute('aria-controls')!)!
  fireEvent.click(await within(list).findByText(value, {}, { timeout: 2000 }))
}

const approveBtn = () => screen.getByRole('button', { name: 'Approve model' })

describe('ArchitecturePage', () => {
  it('renders the tables from the response', async () => {
    renderPage()
    expect(await screen.findByRole('table', { name: 'People and systems' })).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Containers' })).toBeInTheDocument()
    expect(screen.getByText('Team Web')).toBeInTheDocument()
    expect(screen.getByText('holds the checkout')).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Components of C2 Orders API' })).toBeInTheDocument()
    const paths = screen.getByRole('table', { name: 'Paths' })
    expect(within(paths).getByText('OAuth token')).toBeInTheDocument()
    expect(within(paths).getByText('ENV1: TB1')).toBeInTheDocument()
    expect(within(screen.getByRole('table', { name: 'Trust boundaries' })).getByText('the load balancer')).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Deployment and infrastructure' })).toBeInTheDocument()
    expect(within(screen.getByRole('table', { name: 'Sequences' })).getByText(/1\. R1/)).toBeInTheDocument()
    expect(screen.getByText('1 open, 1 pending')).toBeInTheDocument()
    expect(screen.getByText('MODEL-1')).toBeInTheDocument()
  })

  it('renders nothing for an empty table', async () => {
    const rec = { ...RECORD, views: {}, rels: {} }
    model = c4({ latest_record: rec })
    renderPage()
    await screen.findByRole('table', { name: 'Containers' })
    expect(screen.queryByRole('table', { name: 'Paths' })).toBeNull()
    expect(screen.queryByRole('table', { name: 'Sequences' })).toBeNull()
    expect(screen.queryByText('Paths')).toBeNull()
  })

  it('selecting C2 shows its risks and those on its components and paths', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Select C2' }))
    const detail = await screen.findByRole('region', { name: 'Details of C2' })
    await waitFor(() => expect(within(detail).getByText('Title RISK-1', { exact: false })).toBeInTheDocument())
    expect(within(detail).getByText('Risks on C2')).toBeInTheDocument()
    expect(within(detail).getByText('Risks on its paths and components')).toBeInTheDocument()
    expect(within(detail).getByText('Title RISK-2', { exact: false })).toBeInTheDocument()
    expect(within(detail).queryByText('Title RISK-3', { exact: false })).toBeNull()
  })

  it('approve posts the shown sha256', async () => {
    renderPage()
    await typeNote()
    await waitFor(() => expect(approveBtn()).toBeEnabled())
    fireEvent.click(approveBtn())
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].url).toBe('/api/main/systems/demo/c4/approve')
    expect(posts[0].body).toEqual({ note: NOTE, expected_sha256: 'sha-seen' })
  })

  it('shows added, removed, changed fields and the diff', async () => {
    renderPage()
    expect(await screen.findByText('C3')).toBeInTheDocument()
    expect(screen.getByText('C9')).toBeInTheDocument()
    expect(screen.getByText('C2: description, technology')).toBeInTheDocument()
    expect(screen.getByLabelText('Changes to workspace.dsl')).toHaveTextContent('+new line')
  })

  it('a 409 reloads and keeps Approve off until the reload lands', async () => {
    renderPage()
    await typeNote()
    await waitFor(() => expect(approveBtn()).toBeEnabled())
    let release!: () => void
    getGate = new Promise((r) => (release = r))
    postReply = () => json({ detail: 'changed', current_sha256: 'x' }, 409)
    model = c4({ preview: { ...c4().preview!, sha256: 'sha-new' } })
    fireEvent.click(approveBtn())
    expect(await screen.findByText(/workspace.dsl changed since it was shown/)).toBeInTheDocument()
    expect(approveBtn()).toBeDisabled()
    release()
    await waitFor(() => expect(approveBtn()).toBeEnabled())
    fireEvent.click(approveBtn())
    await waitFor(() => expect(posts).toHaveLength(2))
    expect(posts[1].body.expected_sha256).toBe('sha-new')
  })

  it('shows the Terminal hint for a refusal', async () => {
    postReply = () => json({ detail: 'c4 approve needs an interactive terminal' }, 422)
    renderPage()
    await typeNote()
    await waitFor(() => expect(approveBtn()).toBeEnabled())
    fireEvent.click(approveBtn())
    expect(await screen.findByText(/webapp\/start\.command/)).toBeInTheDocument()
  })

  it('counts the note and keeps Approve off until it is long enough', async () => {
    renderPage()
    await typeNote('short')
    expect(screen.getByText('5 of at least 20 characters.')).toBeInTheDocument()
    expect(approveBtn()).toBeDisabled()
  })

  it.each([
    ['accepted', null, 'Structurizr accepted this file.'],
    ['refused', 'line 3: boom', 'Structurizr refused this file: line 3: boom'],
    ['not-checked', null, 'Not checked yet: open the diagrams to check.'],
  ] as const)('verdict %s', async (state, message, text) => {
    model = c4({ structurizr: { state, message, base: null, views: [] } })
    renderPage()
    expect(await screen.findByTestId('verdict')).toHaveTextContent(text)
  })

  it('shows a refused verdict message escaped, as text', async () => {
    model = c4({ structurizr: { state: 'refused', message: '<img src=x onerror=1>‮', base: null, views: [] } })
    renderPage()
    const v = await screen.findByTestId('verdict')
    expect(v.querySelector('img')).toBeNull()
    expect(v).toHaveTextContent('<img src=x onerror=1>\\u202e')
  })

  it('test_export_unavailable_message', async () => {
    postReply = () => json({ detail: 'Docker is not available.' }, 503)
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Open diagrams' }))
    expect(await screen.findByText('Docker is not available.')).toBeInTheDocument()
    expect(posts[0].url).toBe('/api/main/systems/demo/c4/export')
  })

  it('lists the views from the export as safe links', async () => {
    postReply = () =>
      json({ sha256: 's', state: 'accepted', message: null, base: '/diagrams/main/demo/s/', views: [{ key: 'containers', url: '/diagrams/main/demo/s/#containers' }] })
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Open diagrams' }))
    const link = await screen.findByRole('link', { name: 'containers' })
    expect(link).toHaveAttribute('href', '/diagrams/main/demo/s/#containers')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noreferrer noopener')
  })

  it('routes show the against-the-arrow marker', async () => {
    routesReply = () =>
      json({
        chains: [
          { hops: [{ path: 'R1', from: 'C2', to: 'C1', against_arrow: true, crossings: { ENV1: ['TB1'] }, risks: { open: ['RISK-2'], pending: [] } }], elements: {} },
        ],
      })
    renderPage()
    await screen.findByRole('table', { name: 'Containers' })
    for (const [label, value] of [['From', 'C2 Orders API'], ['To', 'C1 Web app']]) {
      await pick(label, value)
    }
    expect(await screen.findByText('against the arrow')).toBeInTheDocument()
    expect(screen.getByText('ENV1 crosses TB1')).toBeInTheDocument()
    expect(screen.getByText('Risks open: RISK-2')).toBeInTheDocument()
  })

  it('shows the too-broad error from the routes call', async () => {
    routesReply = () => json({ detail: 'this route search is too broad: pick endpoints closer together' }, 422)
    renderPage()
    await screen.findByRole('table', { name: 'Containers' })
    for (const [label, value] of [['From', 'C2 Orders API'], ['To', 'C1 Web app']]) {
      await pick(label, value)
    }
    expect(await screen.findByText(/too broad/)).toBeInTheDocument()
  })

  it('test_no_model_yet', async () => {
    model = c4({ preview: null, latest_record: null, approvals: [], status: { state: 'none', latest: null, current_sha256: null }, text: '' })
    renderPage()
    expect(
      await screen.findByText("There's no C4 model for this system yet. The modeling agent drafts one in systems/demo/workspace.dsl."),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open diagrams' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Approve model' })).toBeNull()
  })

  it('shows a file error in an Alert', async () => {
    model = c4({ preview: null, error: 'workspace.dsl: line 4 bad', status: { state: 'changed', latest: null, current_sha256: 'c' } })
    renderPage()
    expect(await screen.findByText('workspace.dsl: line 4 bad')).toBeInTheDocument()
    await typeNote()
    expect(approveBtn()).toBeDisabled()
  })

  it.each([
    ['problems', { problems: ['line 3: C1 needs a role'] }, 'line 3: C1 needs a role'],
    ['reused IDs', { reused: ['C7'] }, /cannot be reused: C7/],
    ['adoption gaps', { adoption: { gaps: [{ id: 'E4', cited_by: ['RISK-1'] }], pending_rereviews: [] } }, /E4 is cited by RISK-1/],
    ['pending re-reviews', { adoption: { gaps: [], pending_rereviews: ['RISK-9'] } }, /RISK-9 awaits re-review/],
  ] as [string, Partial<NonNullable<C4Response['preview']>>, string | RegExp][])('%s disable approval with the reason shown', async (_n, over, reason) => {
    model = c4({ preview: { ...c4().preview!, ...over } })
    renderPage()
    await typeNote()
    expect(await screen.findByText(reason)).toBeInTheDocument()
    expect(approveBtn()).toBeDisabled()
  })

  it('shows stored text with a bidi control escaped', async () => {
    const rec = { ...RECORD, items: { ...RECORD.items, C1: { ...RECORD.items.C1, name: 'Web‮app' } } }
    model = c4({ latest_record: rec })
    renderPage()
    expect(await screen.findAllByText('Web\\u202eapp')).not.toHaveLength(0)
    expect(document.body.textContent).not.toContain('‮')
  })
})
