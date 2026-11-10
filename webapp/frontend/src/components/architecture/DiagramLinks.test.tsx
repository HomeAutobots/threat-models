import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../../api/queries'
import { DiagramLinks } from './DiagramLinks'

function mount() {
  render(
    <MantineProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <DiagramLinks reg="main" slug="demo" />
      </QueryClientProvider>
    </MantineProvider>,
  )
}

describe('DiagramLinks', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('shows no links before the export', () => {
    mount()
    expect(screen.queryByRole('link')).toBeNull()
  })

  it('shows a 503 detail escaped', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'No Docker‮' }), { status: 503 })))
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'Open diagrams' }))
    expect(await screen.findByText('No Docker\\u202e')).toBeInTheDocument()
  })
})
