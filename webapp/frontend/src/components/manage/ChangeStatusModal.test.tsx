import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../../api/queries'
import type { Meta, Risk } from '../../api/types'
import { ChangeStatusModal } from './ChangeStatusModal'

const meta = { statuses: ['open', 'mitigated', 'accepted'], note_min: 20 } as unknown as Meta
const risk = { id: 'T-1', status: 'open', review_state: 'approved', title: 'A' } as Risk

let posts: { url: string; body: any }[]
let reply: () => Response

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function renderModal(onClose = vi.fn()) {
  render(
    <MantineProvider env="test">
      <QueryClientProvider client={makeQueryClient()}>
        <ChangeStatusModal reg="main" slug="demo" risk={risk} meta={meta} opened onClose={onClose} />
      </QueryClientProvider>
    </MantineProvider>,
  )
  return onClose
}

beforeEach(() => {
  posts = []
  reply = () => json({ risk: { ...risk, status: 'mitigated' } })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        posts.push({ url, body: JSON.parse(String(init.body)) })
        return reply()
      }
      return json({})
    }),
  )
})

describe('ChangeStatusModal', () => {
  it('posts {fields: {status}} with seen and the reason', async () => {
    const onClose = renderModal()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('combobox', { name: 'Status' }))
    await user.click(await screen.findByRole('option', { name: 'mitigated' }))
    fireEvent.change(screen.getByLabelText('Reason (optional)'), { target: { value: 'Fixed in prod' } })
    await user.click(screen.getByRole('button', { name: 'Save status' }))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].url).toBe('/api/main/systems/demo/risks/T-1/edit')
    expect(posts[0].body).toEqual({ fields: { status: 'mitigated' }, seen: risk, reason: 'Fixed in prod' })
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('a double click posts once', async () => {
    renderModal()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('combobox', { name: 'Status' }))
    await user.click(await screen.findByRole('option', { name: 'accepted' }))
    const save = screen.getByRole('button', { name: 'Save status' })
    fireEvent.click(save)
    fireEvent.click(save)
    await waitFor(() => expect(posts).toHaveLength(1))
  })

  it('shows the stale text on 409 and the escaped detail on 422', async () => {
    reply = () => json({ detail: 'x', current: { ...risk, title: 'B' } }, 409)
    renderModal()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('combobox', { name: 'Status' }))
    await user.click(await screen.findByRole('option', { name: 'accepted' }))
    await user.click(screen.getByRole('button', { name: 'Save status' }))
    expect(await screen.findByText(/This risk changed after you opened it\. Review the current version\./)).toBeInTheDocument()
  })

  it('escapes a 422 detail', async () => {
    reply = () => json({ detail: 'bad‮gnp' }, 422)
    renderModal()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('combobox', { name: 'Status' }))
    await user.click(await screen.findByRole('option', { name: 'accepted' }))
    await user.click(screen.getByRole('button', { name: 'Save status' }))
    expect(await screen.findByText('bad\\u202egnp')).toBeInTheDocument()
  })

  it('after a 409 the next submit posts seen equal to current, with the typed reason and chosen status', async () => {
    const current = { ...risk, title: 'B', status: 'accepted' } as Risk
    reply = () => json({ detail: 'x', current }, 409)
    renderModal()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('combobox', { name: 'Status' }))
    await user.click(await screen.findByRole('option', { name: 'mitigated' }))
    fireEvent.change(screen.getByLabelText('Reason (optional)'), { target: { value: 'because' } })
    await user.click(screen.getByRole('button', { name: 'Save status' }))
    expect(await screen.findByText(/Review the current version\. Current status: accepted\./)).toBeInTheDocument()
    reply = () => json({ risk: current })
    await user.click(screen.getByRole('button', { name: 'Save status' }))
    await waitFor(() => expect(posts).toHaveLength(2))
    expect(posts[1].body).toEqual({ fields: { status: 'mitigated' }, seen: current, reason: 'because' })
  })
})
