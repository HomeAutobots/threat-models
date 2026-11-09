import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../../api/queries'
import type { Risk } from '../../api/types'
import { RetireModal } from './RetireModal'

const risk = { id: 'T-1', status: 'open', review_state: 'approved', title: 'A' } as Risk
const CONFIRM = "Retire T-1? It stays in the register under Retired and can't be edited."

let posts: { url: string; body: any }[]
let reply409: Risk | 'no-current' | null

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  posts = []
  reply409 = null
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        posts.push({ url, body: JSON.parse(String(init.body)) })
        if (reply409 === 'no-current') return json({ detail: 'x' }, 409)
        if (reply409) return json({ detail: 'x', current: reply409 }, 409)
        return json({ risk: { ...risk, status: 'retired' } })
      }
      return json({})
    }),
  )
})

function renderModal(onClose = vi.fn()) {
  render(
    <MantineProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <RetireModal reg="main" slug="demo" risk={risk} noteMin={20} opened onClose={onClose} />
      </QueryClientProvider>
    </MantineProvider>,
  )
  return onClose
}

describe('RetireModal', () => {
  it('needs 20 characters and a confirmation before it posts', async () => {
    const onClose = renderModal()
    const box = await screen.findByLabelText('Reason')
    const retire = screen.getByRole('button', { name: 'Retire T-1' })
    expect(retire).toBeDisabled()
    fireEvent.change(box, { target: { value: `  ${'x'.repeat(19)}  ` } })
    expect(screen.getByText('19 / 20')).toBeInTheDocument()
    expect(retire).toBeDisabled()
    const reason = 'x'.repeat(20)
    fireEvent.change(box, { target: { value: reason } })
    expect(retire).toBeEnabled()
    fireEvent.click(retire)
    expect(posts).toHaveLength(0)
    expect(screen.getByText(CONFIRM)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retire' }))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].url).toBe('/api/main/systems/demo/risks/T-1/retire')
    expect(posts[0].body).toEqual({ reason, seen: risk })
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('strips outer whitespace the way Python does: U+001C and U+0085 go, U+FEFF stays', async () => {
    renderModal()
    const box = await screen.findByLabelText('Reason')
    fireEvent.change(box, { target: { value: `\u001c\u0085${'x'.repeat(5)}\u0085` } })
    expect(screen.getByText('5 / 20')).toBeInTheDocument()
    fireEvent.change(box, { target: { value: `\ufeff${'x'.repeat(19)}` } })
    expect(screen.getByText('20 / 20')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retire T-1' })).toBeEnabled()
  })

  it('counts the reason in code points, as core does', async () => {
    renderModal()
    fireEvent.change(await screen.findByLabelText('Reason'), { target: { value: '😀'.repeat(20) } })
    expect(screen.getByText('20 / 20')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retire T-1' })).toBeEnabled()
  })

  it('Cancel on the confirmation posts nothing', async () => {
    renderModal()
    fireEvent.change(await screen.findByLabelText('Reason'), { target: { value: 'x'.repeat(20) } })
    fireEvent.click(screen.getByRole('button', { name: 'Retire T-1' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(posts).toHaveLength(0)
    expect(screen.queryByText(CONFIRM)).not.toBeInTheDocument()
  })

  it('a double click on Retire posts once', async () => {
    renderModal()
    fireEvent.change(await screen.findByLabelText('Reason'), { target: { value: 'x'.repeat(20) } })
    fireEvent.click(screen.getByRole('button', { name: 'Retire T-1' }))
    const go = screen.getByRole('button', { name: 'Retire' })
    fireEvent.click(go)
    fireEvent.click(go)
    await waitFor(() => expect(posts).toHaveLength(1))
  })

  it('after a 409 the next submit posts seen equal to current, with the typed reason', async () => {
    const current = { ...risk, title: 'B', status: 'accepted' } as Risk
    reply409 = current
    renderModal()
    const reason = 'y'.repeat(25)
    fireEvent.change(await screen.findByLabelText('Reason'), { target: { value: reason } })
    fireEvent.click(screen.getByRole('button', { name: 'Retire T-1' }))
    fireEvent.click(screen.getByRole('button', { name: 'Retire' }))
    expect(await screen.findByText(/Review the current version\. Current status: accepted\./)).toBeInTheDocument()
    expect((screen.getByLabelText('Reason') as HTMLTextAreaElement).value).toBe(reason)
    reply409 = null
    fireEvent.click(screen.getByRole('button', { name: 'Retire T-1' }))
    fireEvent.click(screen.getByRole('button', { name: 'Retire' }))
    await waitFor(() => expect(posts).toHaveLength(2))
    expect(posts[1].body).toEqual({ reason, seen: current })
  })

  it('escapes the risk ID in the title, the button and the confirmation', async () => {
    const hostile = { ...risk, id: 'T\u202e1' } as Risk
    render(
      <MantineProvider>
        <QueryClientProvider client={makeQueryClient()}>
          <RetireModal reg="main" slug="demo" risk={hostile} noteMin={20} opened onClose={vi.fn()} />
        </QueryClientProvider>
      </MantineProvider>,
    )
    expect(await screen.findByText('Retire T\\u202e1', { selector: 'h2' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'x'.repeat(20) } })
    fireEvent.click(screen.getByRole('button', { name: 'Retire T\\u202e1' }))
    expect(screen.getByText(/^Retire T\\u202e1\? /)).toBeInTheDocument()
  })

  it('a 409 without current shows the banner and adopts the refetched risk as seen', async () => {
    const refetched = { ...risk, status: 'accepted' } as Risk
    const ui = (r: Risk) => (
      <MantineProvider>
        <QueryClientProvider client={client}>
          <RetireModal reg="main" slug="demo" risk={r} noteMin={20} opened onClose={vi.fn()} />
        </QueryClientProvider>
      </MantineProvider>
    )
    const client = makeQueryClient()
    const { rerender } = render(ui(risk))
    reply409 = 'no-current'
    const reason = 'y'.repeat(25)
    fireEvent.change(await screen.findByLabelText('Reason'), { target: { value: reason } })
    fireEvent.click(screen.getByRole('button', { name: 'Retire T-1' }))
    fireEvent.click(screen.getByRole('button', { name: 'Retire' }))
    expect(await screen.findByText(/This risk changed after you opened it/)).toBeInTheDocument()
    rerender(ui(refetched))
    expect(await screen.findByText(/Current status: accepted\./)).toBeInTheDocument()
    reply409 = null
    fireEvent.click(screen.getByRole('button', { name: 'Retire T-1' }))
    fireEvent.click(screen.getByRole('button', { name: 'Retire' }))
    await waitFor(() => expect(posts).toHaveLength(2))
    expect(posts[1].body).toEqual({ reason, seen: refetched })
  })
})
