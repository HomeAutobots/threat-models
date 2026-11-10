import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from '../../api/queries'
import type { StructurizrVerdict } from '../../api/types'
import { DiagramLinks } from './DiagramLinks'

let verdict: StructurizrVerdict = { state: 'not-checked', message: null, base: null, views: [] }

function mount() {
  render(
    <MantineProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <DiagramLinks reg="main" slug="demo" sha256="abcdef0123456789" version="1.4" verdict={verdict} />
      </QueryClientProvider>
    </MantineProvider>,
  )
}

describe('DiagramLinks', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
    verdict = { state: 'not-checked', message: null, base: null, views: [] }
  })

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

  it('links the views of an accepted export of this very file, labelled with its version and sha', () => {
    verdict = { state: 'accepted', message: null, base: '/diagrams/main/demo/abcdef/', views: [{ key: 'containers', url: '/diagrams/main/demo/abcdef/#containers' }] }
    mount()
    const link = screen.getByRole('link', { name: 'containers' })
    expect(link).toHaveAttribute('href', '/diagrams/main/demo/abcdef/#containers')
    expect(link).toHaveAttribute('rel', 'noreferrer noopener')
    expect(screen.getByText('Diagrams for version 1.4, sha256 abcdef0123456789')).toBeInTheDocument()
  })
})

