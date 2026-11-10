import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../../api/queries'
import { c4 } from '../../test-c4'
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
