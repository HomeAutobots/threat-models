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
let reply409: Risk | null

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
})
