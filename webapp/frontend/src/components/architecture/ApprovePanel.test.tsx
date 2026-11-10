import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../../api/queries'
import { RECORD, c4 } from '../../test-c4'
import { ApprovePanel, verdictText } from './ApprovePanel'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      new Response(JSON.stringify(url === '/api/meta' ? { note_min: 20 } : c4()), { status: 200 }),
    ),
  )
})

describe('ApprovePanel', () => {
  it('verdict texts', () => {
    const v = { message: null, base: null, views: [] }
    expect(verdictText({ ...v, state: 'accepted' })).toBe('Structurizr accepted this file.')
    expect(verdictText({ ...v, state: 'not-checked' })).toBe('Not checked yet: open the diagrams to check.')
    expect(verdictText({ ...v, state: 'refused', message: 'bad' })).toBe('Structurizr refused this file: bad')
  })

  it('shows a properties change one line per changed key, sorted, without tm.was', async () => {
    const withProps = (props: Record<string, string>) => ({
      ...RECORD,
      items: { ...RECORD.items, C1: { ...RECORD.items.C1, properties: props } },
    })
    const old = withProps({ 'tm.zoom': 'holds the checkout', 'tm.owner': 'Team Web', 'tm.was': 'P1' })
    const now = withProps({ 'tm.zoom': 'holds the checkout', 'tm.owner': 'Team Pay', 'tm.assumed': 'no input names the owner', 'tm.was': 'P1, P3' })
    const data = c4({ latest_record: old, preview: { ...c4().preview!, record: now, changed: { C1: ['properties'] } } })
    render(
      <MantineProvider>
        <QueryClientProvider client={makeQueryClient()}>
          <ApprovePanel reg="main" slug="demo" data={data} />
        </QueryClientProvider>
      </MantineProvider>,
    )
    expect(await screen.findByText('property tm.assumed: (none) → no input names the owner')).toBeInTheDocument()
    expect(screen.getAllByText(/^property /).map((e) => e.textContent)).toEqual([
      'property tm.assumed: (none) → no input names the owner',
      'property tm.owner: Team Web → Team Pay',
    ])
    expect(screen.queryByText(/tm\.was|tm\.zoom|"tm\./)).toBeNull() // no JSON bags, no tm.was
  })

  it('keeps Approve off when the file matches the latest approval', async () => {
    const data = c4({ status: { state: 'current', latest: null, current_sha256: 'x' } })
    render(
      <MantineProvider>
        <QueryClientProvider client={makeQueryClient()}>
          <ApprovePanel reg="main" slug="demo" data={data} />
        </QueryClientProvider>
      </MantineProvider>,
    )
    fireEvent.change(await screen.findByLabelText('Approval note'), { target: { value: 'a long enough careful note' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Approve model' })).toBeDisabled())
  })
})
