import { MantineProvider } from '@mantine/core'
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import reviewPageSrc from './ReviewPage.tsx?raw'
import panelSrc from '../components/review/DecisionPanel.tsx?raw'
import diffSrc from '../components/review/ReReviewDiff.tsx?raw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DecisionPanelProps } from '../components/review/DecisionPanel'
import { makeQueryClient } from '../api/queries'
import type { Risk, RiskDetail } from '../api/types'
import { ReviewPage } from './ReviewPage'

// Every render of the panel and the record, in commit order, so a test can see a render that a
// DOM observer would miss (both renders commit before its first callback).
const renders = vi.hoisted(() => ({
  panel: [] as { busy: boolean; dup: string | null | undefined }[],
  dup: null as string | null | undefined,
}))
vi.mock('../components/record/RiskRecord', async (orig) => {
  const m = await orig<typeof import('../components/record/RiskRecord')>()
  return {
    ...m,
    RiskRecord: (p: { detail: RiskDetail; meta: unknown; history: unknown[]; reloading?: boolean }) => {
      renders.dup = p.reloading ? null : p.detail.duplicate?.title
      return <m.RiskRecord {...(p as Parameters<typeof m.RiskRecord>[0])} />
    },
  }
})
vi.mock('../components/review/DecisionPanel', async (orig) => {
  const m = await orig<typeof import('../components/review/DecisionPanel')>()
  return {
    ...m,
    DecisionPanel: (p: DecisionPanelProps) => {
      renders.panel.push({ busy: p.busy, dup: renders.dup })
      return <m.DecisionPanel {...p} />
    },
  }
})

const STALE = 'This risk changed after you opened it. Review the current version.'
const NOTE = 'This is a careful review note.'

const meta = {
  fields: [],
  editable: ['title', 'notes'],
  labels: { title: 'Title', notes: 'Notes' },
  stride: {},
  linddun: [],
  note_min: 20,
}

function mkRisk(id: string, over: Partial<Risk> = {}): Risk {
  return {
    id,
    title: `Title of ${id}`,
    notes: `Original notes of ${id}`,
    review_state: 'pending',
    last_approved: null,
    possible_duplicate_of: null,
    elements: [],
    ...over,
  } as Risk
}

function mkDetail(risk: Risk, over: Partial<RiskDetail> = {}): RiskDetail {
  return {
    risk,
    elements: {},
    dfd: { state: 'current', latest_id: 'DFD-1', written_against: 'DFD-1', error: null },
    editors_since_approval: [],
    duplicate: null,
    ...over,
  }
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

interface Post {
  url: string
  body: { note: string; seen: Risk; into?: string }
}

let details: Record<string, RiskDetail>
let queue: Risk[]
let posts: Post[]
let getGate: Promise<void> | null = null
let postReply: (post: Post) => Response | Promise<Response>
let failList: boolean
let failRisk: boolean
let historyGets: number
let historyGate: Promise<void> | null
let failHistory: boolean
let historyBody: unknown[]

function mockApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        const post = { url, body: JSON.parse(String(init.body)) } as Post
        posts.push(post)
        return postReply(post)
      }
      if (url === '/api/meta') return json(meta)
      if (url.endsWith('/history')) {
        historyGets++
        if (historyGate) await historyGate
        if (failHistory) return json({ detail: 'history failed' }, 404)
        return json(historyBody)
      }
      const m = url.match(/\/risks\/([^/]+)$/)
      if (m && getGate) await getGate
      if (m && failRisk) return json({ detail: 'risk fetch failed \u202e' }, 404)
      if (url.endsWith('/risks') && failList) return json({ detail: 'list <b> \u202e failed' }, 404)
      if (m)
        return details[decodeURIComponent(m[1])]
          ? json(details[decodeURIComponent(m[1])])
          : json({ detail: 'none' }, 404)
      if (url.endsWith('/risks')) return json(queue)
      return json({}, 404)
    }),
  )
}

function Where() {
  const loc = useLocation()
  return <div data-testid="where">{loc.pathname + loc.search}</div>
}

function renderPage(initial = '/main/demo/review', client: QueryClient = makeQueryClient()) {
  render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[initial]}>
          <Routes>
            <Route path="/:reg/:slug/review" element={<ReviewPage />} />
            <Route path="*" element={<Where />} />
          </Routes>
          <Where />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  )
  return client
}

async function type(note = NOTE) {
  const box = await screen.findByLabelText('Review note')
  fireEvent.change(box, { target: { value: note } })
  return box as HTMLTextAreaElement
}

beforeEach(() => {
  posts = []
  getGate = null
  failList = false
  failRisk = false
  historyGets = 0
  historyGate = null
  failHistory = false
  historyBody = []
  queue = [mkRisk('T-1'), mkRisk('T-2'), mkRisk('T-3')]
  details = Object.fromEntries(queue.map((r) => [r.id, mkDetail(r)]))
  postReply = (p) => json({ risk: { ...p.body.seen, review_state: 'approved' } })
  mockApi()
})

describe('ReviewPage', () => {
  it('shows the first pending risk and the position, in API order', async () => {
    queue = [mkRisk('T-9', { review_state: 'approved' }), ...queue]
    renderPage()
    expect(await screen.findByText('1 of 3 pending')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve T-1' })).toBeInTheDocument()
  })

  it('renders no nested main landmark, and the record title is the only h1', async () => {
    renderPage()
    expect(await screen.findByText('1 of 3 pending')).toBeInTheDocument()
    expect(document.querySelector('main')).toBeNull()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
  })

  it('?id= selects the item, and Previous and Next only navigate', async () => {
    renderPage('/main/demo/review?id=T-2')
    expect(await screen.findByText('2 of 3 pending')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('3 of 3 pending')).toBeInTheDocument()
    expect(screen.getByTestId('where').textContent).toContain('id=T-3')
    fireEvent.click(screen.getByRole('button', { name: 'Previous' }))
    expect(await screen.findByText('2 of 3 pending')).toBeInTheDocument()
    expect(posts).toHaveLength(0)
  })

  it('approve posts note and the record exactly as received, then moves to the next', async () => {
    postReply = (p) => {
      queue = queue.slice(1) // the write lands before the refetch
      return json({ risk: { ...p.body.seen, review_state: 'approved' } })
    }
    renderPage()
    await type()
    fireEvent.click(await screen.findByRole('button', { name: 'Approve T-1' }))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].url).toBe('/api/main/systems/demo/risks/T-1/approve')
    expect(posts[0].body).toEqual({ note: NOTE, seen: details['T-1'].risk })
    expect(await screen.findByRole('button', { name: 'Approve T-2' })).toBeInTheDocument()
    expect(screen.getByTestId('where').textContent).toContain('id=T-2')
    expect((screen.getByLabelText('Review note') as HTMLTextAreaElement).value).toBe('')
  })

  it('says so when no risks are waiting after the last decision', async () => {
    queue = [mkRisk('T-1')]
    details = { 'T-1': mkDetail(queue[0]) }
    postReply = (p) => {
      queue = [] // the write lands before the refetch
      return json({ risk: { ...p.body.seen, review_state: 'approved' } })
    }
    renderPage()
    await type()
    fireEvent.click(await screen.findByRole('button', { name: 'Approve T-1' }))
    expect(await screen.findByText('No risks are waiting for review.')).toBeInTheDocument()
    expect(screen.queryByText(STALE)).not.toBeInTheDocument()
  })

  it('says so at once when the queue is empty', async () => {
    queue = []
    renderPage()
    expect(await screen.findByText('No risks are waiting for review.')).toBeInTheDocument()
  })

  it('stale keeps the note', async () => {
    postReply = (p) =>
      p.body.seen.notes === 'changed by AI'
        ? json({ risk: { ...p.body.seen, review_state: 'approved' } })
        : (() => {
            const current = mkRisk('T-1', { notes: 'changed by AI' })
            details['T-1'] = mkDetail(current) // the server now serves the new record
            return json({ detail: 'stale', current }, 409)
          })()
    renderPage()
    const box = await type()
    fireEvent.click(await screen.findByRole('button', { name: 'Approve T-1' }))
    expect(await screen.findByText(STALE)).toBeInTheDocument()
    expect(box.value).toBe(NOTE)
    expect(screen.getByText('changed by AI')).toBeInTheDocument()
    expect(screen.queryByText('Original notes of T-1')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Approve T-1' }))
    await waitFor(() => expect(posts).toHaveLength(2))
    expect(posts[1].body.seen.notes).toBe('changed by AI')
    expect(posts[1].body.note).toBe(NOTE)
  })

  it('a later fetch that differs without a 409 is swapped in with the stale banner', async () => {
    const client = renderPage()
    await type()
    expect(await screen.findByText('Original notes of T-1')).toBeInTheDocument()
    expect(screen.queryByText(STALE)).not.toBeInTheDocument()
    details['T-1'] = mkDetail(mkRisk('T-1', { notes: 'rewritten behind your back' }))
    await act(async () => {
      await client.invalidateQueries({ queryKey: ['main', 'demo', 'risk', 'T-1'] })
    })
    expect(await screen.findByText(STALE)).toBeInTheDocument()
    expect(screen.getByText('rewritten behind your back')).toBeInTheDocument()
    expect((screen.getByLabelText('Review note') as HTMLTextAreaElement).value).toBe(NOTE)
    fireEvent.click(screen.getByRole('button', { name: 'Approve T-1' }))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].body.seen.notes).toBe('rewritten behind your back')
  })

  it('a refetch that changes nothing shows no banner', async () => {
    const client = renderPage()
    await screen.findByText('Original notes of T-1')
    details['T-1'] = mkDetail(mkRisk('T-1'))
    await act(async () => {
      await client.invalidateQueries({ queryKey: ['main', 'demo', 'risk', 'T-1'] })
    })
    expect(screen.queryByText(STALE)).not.toBeInTheDocument()
  })

  it('shows core 422 detail in the panel (control and bidi characters escaped) and keeps the note', async () => {
    postReply = () => json({ detail: 'Core says: <b>no</b> \u202e approve' }, 422)
    renderPage()
    const box = await type()
    fireEvent.click(await screen.findByRole('button', { name: 'Approve T-1' }))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('Core says: <b>no</b> \\u202e approve')
    expect(box.value).toBe(NOTE)
    expect(screen.queryByText(STALE)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve T-1' })).toBeEnabled()
  })

  it('disables every button while a request is in flight, so a double click sends once', async () => {
    let release: (r: Response) => void = () => {}
    postReply = () => new Promise<Response>((res) => (release = res))
    renderPage()
    await type()
    const approve = await screen.findByRole('button', { name: 'Approve T-1' })
    fireEvent.click(approve)
    fireEvent.click(approve)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reject T-1' })).toBeDisabled())
    for (const name of ['Approve T-1', 'Edit before deciding', 'Previous', 'Next']) {
      expect(screen.getByRole('button', { name })).toBeDisabled()
    }
    fireEvent.click(approve)
    expect(posts).toHaveLength(1)
    await act(async () => release(json({ detail: 'nope' }, 422)))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Approve T-1' })).toBeEnabled())
  })

  it('reject posts to reject', async () => {
    renderPage()
    await type()
    fireEvent.click(await screen.findByRole('button', { name: 'Reject T-1' }))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].url).toBe('/api/main/systems/demo/risks/T-1/reject')
  })

  it('a re-review shows the diff above the record, and restores on reject', async () => {
    const r = mkRisk('T-1', {
      notes: 'proposed notes',
      last_approved: { title: 'Title of T-1', notes: 'approved notes' },
    })
    queue = [r]
    details = { 'T-1': mkDetail(r) }
    renderPage()
    const reject = await screen.findByRole('button', { name: 'Reject and restore last approved' })
    expect(reject).toBeInTheDocument()
    expect(screen.getByText('approved notes')).toBeInTheDocument()
    expect(screen.getByText('1 other field unchanged')).toBeInTheDocument()
    const diff = screen.getByText('Last approved')
    const record = document.getElementById('glance') as HTMLElement
    expect(diff.compareDocumentPosition(record) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('merge posts the duplicate as into, with a link to #dup', async () => {
    const r = mkRisk('T-1', { possible_duplicate_of: 'T-0' })
    queue = [r]
    details = { 'T-1': mkDetail(r, { duplicate: mkRisk('T-0', { review_state: 'approved' }) }) }
    renderPage()
    await type()
    const link = await screen.findByRole('link', { name: 'Possible duplicate of T-0.' })
    expect(link).toHaveAttribute('href', '#dup')
    fireEvent.click(screen.getByRole('button', { name: 'Merge into T-0' }))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].url).toBe('/api/main/systems/demo/risks/T-1/merge')
    expect(posts[0].body.into).toBe('T-0')
  })

  it('warns when the DFD has moved on, with a link to the DFD page', async () => {
    details['T-1'] = mkDetail(queue[0], {
      dfd: { state: 'changed', latest_id: 'DFD-2', written_against: 'DFD-1', error: null },
    })
    renderPage()
    expect(
      await screen.findByText(
        'DFD has moved on. This draft was written against DFD-1, and dfd.md has changed since. Element IDs may be out of date.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open the DFD page' })).toHaveAttribute('href', '/main/demo/dfd')
  })

  it('Edit before deciding goes to the edit page and returns to review', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Edit before deciding' }))
    expect((await screen.findAllByTestId('where')).at(-1)?.textContent).toBe('/main/demo/risks/T-1/edit?return=review')
  })

  it('after a 409 the duplicate comparison and elements follow current, and Merge waits for them', async () => {
    const r = mkRisk('T-1', { possible_duplicate_of: 'T-0', elements: ['P7'] })
    queue = [r]
    details = {
      'T-1': mkDetail(r, {
        elements: { P7: { name: 'Seven', type: 'Process' } },
        duplicate: mkRisk('T-0', { review_state: 'approved', title: 'Zero title' }),
      }),
    }
    let release: () => void = () => {}
    postReply = () => {
      const current = mkRisk('T-1', { possible_duplicate_of: 'T-5', elements: ['P7', 'P9'] })
      details = {
        'T-1': mkDetail(current, {
          elements: { P7: { name: 'Seven', type: 'Process' }, P9: { name: 'Nine', type: 'Process' } },
          duplicate: mkRisk('T-5', { review_state: 'approved', title: 'Five title' }),
        }),
      }
      getGate = new Promise<void>((res) => (release = res))
      return json({ detail: 'stale', current }, 409)
    }
    renderPage()
    await type()
    fireEvent.click(await screen.findByRole('button', { name: 'Merge into T-0' }))
    expect(await screen.findByText(STALE)).toBeInTheDocument()
    // The context is still being reloaded: nothing can be decided.
    expect(screen.getByRole('button', { name: 'Merge into T-5' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Approve T-1' })).toBeDisabled()
    await act(async () => release())
    await waitFor(() => expect(screen.getByRole('button', { name: 'Merge into T-5' })).toBeEnabled())
    const dup = document.getElementById('dup') as HTMLElement
    expect(dup.textContent).toContain('T-5')
    expect(dup.textContent).toContain('Five title')
    expect(dup.textContent).not.toContain('Zero title')
    expect(screen.getByText('Nine')).toBeInTheDocument()
    expect(document.getElementById('where')?.textContent).not.toContain('Not in the current DFD')
    expect(screen.getByText(STALE)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Merge into T-5' }))
    await waitFor(() => expect(posts).toHaveLength(2))
    expect(posts[1].body.into).toBe('T-5')
  })

  it('a fetch that landed during a failed request is checked when it fails', async () => {
    const client = makeQueryClient()
    postReply = async () => {
      details['T-1'] = mkDetail(mkRisk('T-1', { notes: 'changed while posting' }))
      await client.invalidateQueries({ queryKey: ['main', 'demo', 'risk', 'T-1'] })
      return json({ detail: 'core refused' }, 422)
    }
    renderPage('/main/demo/review', client)
    const box = await type()
    fireEvent.click(await screen.findByRole('button', { name: 'Approve T-1' }))
    expect(await screen.findByText(STALE)).toBeInTheDocument()
    expect(screen.getByText('changed while posting')).toBeInTheDocument()
    expect(screen.getByText('core refused')).toBeInTheDocument()
    expect(box.value).toBe(NOTE)
  })

  it('pins the shown item into the URL, so a list refetch cannot switch it', async () => {
    const client = renderPage()
    const box = await type()
    expect(await screen.findByText('Original notes of T-1')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/main/demo/review?id=T-1'))
    const fresh = mkRisk('T-0')
    details['T-0'] = mkDetail(fresh)
    queue = [fresh, ...queue]
    await act(async () => {
      await client.invalidateQueries({ queryKey: ['main', 'demo', 'risks'] })
    })
    expect(await screen.findByText('2 of 4 pending')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve T-1' })).toBeInTheDocument()
    expect(box.value).toBe(NOTE)
    expect(screen.getByTestId('where').textContent).toBe('/main/demo/review?id=T-1')
  })

  describe('follow-ups', () => {
    const stale409 = (over: Partial<Risk> = {}, withCurrent = true) => {
      postReply = (p) => {
        if (p.body.seen.notes === 'changed by AI') return json({ risk: { ...p.body.seen, review_state: 'approved' } })
        const current = mkRisk('T-1', { notes: 'changed by AI', ...over })
        details['T-1'] = mkDetail(current)
        return json(withCurrent ? { detail: 'stale', current } : { detail: 'stale' }, 409)
      }
    }
    const invalidateRisk = (client: QueryClient) =>
      act(async () => {
        await client.invalidateQueries({ queryKey: ['main', 'demo', 'risk', 'T-1'], exact: true })
      })

    it('a list-refetch error keeps the item and the note, with a small alert above it', async () => {
      const client = renderPage()
      const box = await type()
      expect(await screen.findByText('Original notes of T-1')).toBeInTheDocument()
      failList = true
      await act(async () => {
        await client.invalidateQueries({ queryKey: ['main', 'demo', 'risks'] })
      })
      expect(await screen.findByText('list <b> \\u202e failed')).toBeInTheDocument()
      expect(screen.getByText('Original notes of T-1')).toBeInTheDocument()
      expect(box.value).toBe(NOTE)
      expect(screen.getByRole('button', { name: 'Approve T-1' })).toBeEnabled()
    })

    it('a list error with no data replaces the page, escaped', async () => {
      failList = true
      renderPage()
      expect(await screen.findByText('list <b> \\u202e failed')).toBeInTheDocument()
      expect(screen.queryByText('1 of 3 pending')).not.toBeInTheDocument()
    })

    it('a risk fetch error with nothing shown replaces the page, escaped', async () => {
      failRisk = true
      details['T-1'] = mkDetail(queue[0])
      renderPage('/main/demo/review')
      expect(await screen.findByText('risk fetch failed \\u202e')).toBeInTheDocument()
    })

    it('shows Reloading this risk… and hides the duplicate and element rows until the reload lands', async () => {
      const r = mkRisk('T-1', { possible_duplicate_of: 'T-0', elements: ['P7'] })
      queue = [r]
      details = {
        'T-1': mkDetail(r, {
          elements: { P7: { name: 'Seven', type: 'Process' } },
          duplicate: mkRisk('T-0', { review_state: 'approved', title: 'Zero title' }),
        }),
      }
      let release: () => void = () => {}
      postReply = () => {
        const current = mkRisk('T-1', { possible_duplicate_of: 'T-5', elements: ['P7'] })
        details = {
          'T-1': mkDetail(current, {
            elements: { P7: { name: 'Seven', type: 'Process' } },
            duplicate: mkRisk('T-5', { review_state: 'approved', title: 'Five title' }),
          }),
        }
        getGate = new Promise<void>((res) => (release = res))
        return json({ detail: 'stale', current }, 409)
      }
      renderPage()
      await type()
      fireEvent.click(await screen.findByRole('button', { name: 'Merge into T-0' }))
      expect(await screen.findByText('Reloading this risk…')).toBeInTheDocument()
      expect(screen.queryByText('Seven')).not.toBeInTheDocument()
      expect((document.getElementById('dup') as HTMLElement).textContent).not.toContain('Zero title')
      expect((document.getElementById('dup') as HTMLElement).textContent).not.toContain('Five title')
      await act(async () => release())
      await waitFor(() => expect(screen.queryByText('Reloading this risk…')).not.toBeInTheDocument())
      expect(screen.getByText('Seven')).toBeInTheDocument()
      expect((document.getElementById('dup') as HTMLElement).textContent).toContain('Five title')
    })

    it('a failed reload shows its message inside the item, and a later successful fetch clears it', async () => {
      stale409()
      const client = renderPage()
      await type()
      failRisk = true
      fireEvent.click(await screen.findByRole('button', { name: 'Approve T-1' }))
      expect(await screen.findByText(/Could not reload this risk/)).toBeInTheDocument()
      // The item is still on the page; the early return for the fetch error did not replace it.
      expect(screen.getByText('1 of 3 pending')).toBeInTheDocument()
      expect(screen.getByText('changed by AI')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Approve T-1' })).toBeDisabled()
      failRisk = false
      await invalidateRisk(client)
      await waitFor(() => expect(screen.getByRole('button', { name: 'Approve T-1' })).toBeEnabled())
      expect(screen.queryByText(/Could not reload this risk/)).not.toBeInTheDocument()
      expect(screen.queryByText('risk fetch failed \\u202e')).not.toBeInTheDocument()
    })

    it('after a 409, buttons stay disabled until the risk query has advanced past it (offline)', async () => {
      stale409()
      const client = renderPage()
      await type()
      const spy = vi.spyOn(client, 'refetchQueries').mockResolvedValue(undefined) // a paused refetch resolves at once
      fireEvent.click(await screen.findByRole('button', { name: 'Approve T-1' }))
      expect(await screen.findByText(STALE)).toBeInTheDocument()
      await waitFor(() => expect(spy).toHaveBeenCalled())
      await act(async () => {})
      expect(screen.getByRole('button', { name: 'Approve T-1' })).toBeDisabled()
      expect(screen.getByRole('button', { name: 'Reject T-1' })).toBeDisabled()
      spy.mockRestore() // back online
      await invalidateRisk(client)
      await act(async () => {
        await client.invalidateQueries({ queryKey: ['main', 'demo', 'risk', 'T-1', 'history'], exact: true })
      })
      await waitFor(() => expect(screen.getByRole('button', { name: 'Approve T-1' })).toBeEnabled())
    })

    it('?id= naming a risk that is not pending is pinned to the first pending one', async () => {
      queue = [mkRisk('T-9', { review_state: 'approved' }), ...queue]
      renderPage('/main/demo/review?id=T-9')
      expect(await screen.findByText('1 of 3 pending')).toBeInTheDocument()
      await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/main/demo/review?id=T-1'))
    })

    it('a 409 without current shows the banner, refetches, and reconciles', async () => {
      stale409({}, false)
      renderPage()
      await type()
      fireEvent.click(await screen.findByRole('button', { name: 'Approve T-1' }))
      expect(await screen.findByText(STALE)).toBeInTheDocument()
      expect(await screen.findByText('changed by AI')).toBeInTheDocument()
      await waitFor(() => expect(screen.getByRole('button', { name: 'Approve T-1' })).toBeEnabled())
      fireEvent.click(screen.getByRole('button', { name: 'Approve T-1' }))
      await waitFor(() => expect(posts).toHaveLength(2))
      expect(posts[1].body.seen.notes).toBe('changed by AI')
    })

    it('the post-409 reload also refetches the risk history', async () => {
      stale409()
      renderPage()
      await type()
      await screen.findByText('Original notes of T-1')
      await waitFor(() => expect(historyGets).toBeGreaterThan(0))
      const before = historyGets
      fireEvent.click(await screen.findByRole('button', { name: 'Approve T-1' }))
      await screen.findByText(STALE)
      await waitFor(() => expect(historyGets).toBe(before + 1))
    })

    it('counts the note in code points', async () => {
      renderPage()
      await type('😀'.repeat(7))
      expect(screen.getByText('7 / 20')).toBeInTheDocument()
    })

    it('Previous and Next drop the note between items', async () => {
      renderPage('/main/demo/review?id=T-2')
      const box = await type()
      expect(box.value).toBe(NOTE)
      fireEvent.click(await screen.findByRole('button', { name: 'Next' }))
      await screen.findByText('3 of 3 pending')
      expect((screen.getByLabelText('Review note') as HTMLTextAreaElement).value).toBe('')
      await type()
      fireEvent.click(screen.getByRole('button', { name: 'Previous' }))
      await screen.findByText('2 of 3 pending')
      expect((screen.getByLabelText('Review note') as HTMLTextAreaElement).value).toBe('')
    })

    describe('reload gate (fix round 1)', () => {
      const setup = () => {
        const r = mkRisk('T-1', { possible_duplicate_of: 'T-0', elements: ['P7'] })
        queue = [r]
        const dfdChanged = { state: 'changed', latest_id: 'DFD-2', written_against: 'DFD-1', error: null } as const
        details = {
          'T-1': mkDetail(r, {
            dfd: dfdChanged,
            elements: { P7: { name: 'Seven', type: 'Process' } },
            duplicate: mkRisk('T-0', { review_state: 'approved', title: 'Zero title' }),
          }),
        }
        postReply = () => {
          const current = mkRisk('T-1', { possible_duplicate_of: 'T-5', elements: ['P7'] })
          details = {
            'T-1': mkDetail(current, {
              dfd: dfdChanged,
              elements: { P7: { name: 'Seven', type: 'Process' } },
              duplicate: mkRisk('T-5', { review_state: 'approved', title: 'Five title' }),
            }),
          }
          return json({ detail: 'stale', current }, 409)
        }
      }
      const DFD_ALERT = /DFD has moved on/
      const dup = () => (document.getElementById('dup') as HTMLElement).textContent as string
      const noOldContext = () => {
        expect(dup()).not.toContain('Zero title')
        expect(dup()).not.toContain('Five title')
        expect(screen.queryByText('Seven')).not.toBeInTheDocument()
        expect(screen.queryByText(DFD_ALERT)).not.toBeInTheDocument()
        expect(document.getElementById('where')?.textContent ?? '').not.toContain('From the current dfd.md')
      }

      it('in the failed state the old context stays hidden and the buttons stay disabled', async () => {
        setup()
        const client = renderPage()
        await type()
        expect(await screen.findByText(DFD_ALERT)).toBeInTheDocument()
        failRisk = true
        fireEvent.click(await screen.findByRole('button', { name: 'Merge into T-0' }))
        expect(await screen.findByText(/Could not reload this risk/)).toBeInTheDocument()
        noOldContext()
        for (const name of ['Approve T-1', 'Reject T-1', 'Merge into T-5']) {
          expect(screen.getByRole('button', { name })).toBeDisabled()
        }
        failRisk = false
        await invalidateRisk(client)
        await waitFor(() => expect(screen.getByRole('button', { name: 'Merge into T-5' })).toBeEnabled())
        expect(dup()).toContain('Five title')
        expect(screen.getByText(DFD_ALERT)).toBeInTheDocument()
      })

      it('keeps Reloading this risk… and the buttons disabled while the history request is pending', async () => {
        setup()
        renderPage()
        await type()
        await screen.findByText('Zero title')
        let release: () => void = () => {}
        historyGate = new Promise<void>((res) => (release = res))
        fireEvent.click(await screen.findByRole('button', { name: 'Merge into T-0' }))
        await waitFor(() => expect(historyGets).toBeGreaterThan(1))
        await act(async () => {
          await new Promise((r) => setTimeout(r, 50)) // the risk refetch has landed by now
        })
        expect(screen.getByText('Reloading this risk…')).toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Approve T-1' })).toBeDisabled()
        noOldContext()
        await act(async () => release())
        await waitFor(() => expect(screen.getByRole('button', { name: 'Merge into T-5' })).toBeEnabled())
        expect(screen.queryByText('Reloading this risk…')).not.toBeInTheDocument()
        expect(dup()).toContain('Five title')
      })

      it('hides the old history while reloading and shows the new one when it lands', async () => {
        setup()
        const row = (seq: number, note: string) => ({
          seq, at: '2026-01-01T00:00:00Z', op: 'edit', tbl: 'risks', row_key: 'T-1',
          actor: 'ai:run-1', diff: {}, note, prev_hash: '', hash: '',
        })
        historyBody = [row(1, 'Old history note')]
        renderPage()
        await type()
        expect(await screen.findByText('Old history note')).toBeInTheDocument()
        let release: () => void = () => {}
        historyGate = new Promise<void>((res) => (release = res))
        historyBody = [row(1, 'Old history note'), row(2, 'New history note')]
        fireEvent.click(await screen.findByRole('button', { name: 'Merge into T-0' }))
        await waitFor(() => expect(historyGets).toBeGreaterThan(1))
        expect(screen.getByText('Reloading this risk…')).toBeInTheDocument()
        expect(screen.queryByText('Old history note')).not.toBeInTheDocument()
        expect(screen.getByText('Reloading history…')).toBeInTheDocument()
        await act(async () => release())
        expect(await screen.findByText('New history note')).toBeInTheDocument()
        expect(screen.queryByText('Reloading history…')).not.toBeInTheDocument()
      })

      it('no render enables the buttons while the replaced context is shown', async () => {
        setup()
        const client = renderPage()
        await type()
        await screen.findByText('Zero title')
        failRisk = true
        fireEvent.click(await screen.findByRole('button', { name: 'Merge into T-0' }))
        await screen.findByText(/Could not reload this risk/)
        failRisk = false
        renders.panel.length = 0
        await invalidateRisk(client)
        await waitFor(() => expect(screen.getByRole('button', { name: 'Merge into T-5' })).toBeEnabled())
        const enabled = renders.panel.filter((x) => !x.busy)
        expect(enabled.length).toBeGreaterThan(0)
        for (const x of enabled) expect(x.dup).toBe('Five title')
      })

      it('a failing history refetch after a 409 keeps the buttons disabled and shows the failure', async () => {
        setup()
        const client = renderPage()
        await type()
        await screen.findByText('Zero title')
        failHistory = true
        fireEvent.click(await screen.findByRole('button', { name: 'Merge into T-0' }))
        expect(await screen.findByText(/Could not reload this risk/)).toBeInTheDocument()
        for (const name of ['Approve T-1', 'Reject T-1', 'Merge into T-5']) {
          expect(screen.getByRole('button', { name })).toBeDisabled()
        }
        noOldContext()
        failHistory = false
        await invalidateRisk(client)
        await act(async () => {
          await client.invalidateQueries({ queryKey: ['main', 'demo', 'risk', 'T-1', 'history'], exact: true })
        })
        await waitFor(() => expect(screen.getByRole('button', { name: 'Merge into T-5' })).toBeEnabled())
      })

      it('stays awaiting when the risk lands before the history, until the history lands', async () => {
        setup()
        const client = renderPage()
        await type()
        await screen.findByText('Zero title')
        let release: () => void = () => {}
        historyGate = new Promise<void>((res) => (release = res))
        failRisk = true
        fireEvent.click(await screen.findByRole('button', { name: 'Merge into T-0' }))
        await screen.findByText(/Could not reload this risk/)
        failRisk = false
        await invalidateRisk(client) // the risk lands through the effect path, history still pending
        await act(async () => {
          await new Promise((r) => setTimeout(r, 50))
        })
        expect(screen.getByRole('button', { name: 'Approve T-1' })).toBeDisabled()
        noOldContext()
        await act(async () => release())
        await waitFor(() => expect(screen.getByRole('button', { name: 'Merge into T-5' })).toBeEnabled())
        expect(dup()).toContain('Five title')
      })

      it('in the failed state only the failure message shows, not the reloading text', async () => {
        setup()
        renderPage()
        await type()
        await screen.findByText('Zero title')
        failRisk = true
        fireEvent.click(await screen.findByRole('button', { name: 'Merge into T-0' }))
        expect(await screen.findByText(/Could not reload this risk/)).toBeInTheDocument()
        expect(screen.queryByText('Reloading this risk…')).not.toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Approve T-1' })).toBeDisabled()
        noOldContext()
      })
    })

    it('keeps the stale banner text in one place', () => {
      expect(reviewPageSrc).not.toContain('This risk changed after you opened it')
    })
  })

  it('uses no raw HTML', () => {
    for (const src of [reviewPageSrc, panelSrc, diffSrc]) expect(src).not.toContain('dangerouslySetInnerHTML')
  })
})
