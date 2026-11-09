import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setCsrf } from '../api/client'
import { makeQueryClient } from '../api/queries'
import { ReportsPage } from './ReportsPage'

let calls: { url: string; headers: Headers }[]

beforeEach(() => {
  calls = []
  setCsrf('tok-1')
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, headers: new Headers(init?.headers) })
      if (url.includes('format=html')) return new Response('<h1>Report</h1>', { status: 200 })
      return new Response('| a | b |', { status: 200 })
    }),
  )
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
})

function renderPage() {
  render(
    <MantineProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <MemoryRouter initialEntries={['/main/demo/reports']}>
          <Routes>
            <Route path="/:reg/:slug/reports" element={<ReportsPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  )
}

describe('ReportsPage', () => {
  it('previews md in a pre with the CSRF header and download=false', async () => {
    renderPage()
    expect(await screen.findByText('| a | b |')).toBeInTheDocument()
    expect(calls[0].url).toContain('format=md')
    expect(calls[0].url).toContain('download=false')
    expect(calls[0].headers.get('X-CSRF-Token')).toBe('tok-1')
  })

  it('html preview is an iframe with an empty sandbox attribute', async () => {
    renderPage()
    fireEvent.click(await screen.findByText('html'))
    const frame = await waitFor(() => {
      const f = document.querySelector('iframe')
      if (!f) throw new Error('no iframe')
      return f
    })
    expect(frame.getAttribute('sandbox')).toBe('')
    expect(frame.getAttribute('srcdoc')).toBe('<h1>Report</h1>')
  })

  it('Download fetches with the header, saves through an object URL, and revokes it later', async () => {
    renderPage()
    await screen.findByText('| a | b |')
    // A microtask queued by the click runs once the click's own task is done: the URL must still
    // be live then, so the browser can start reading the Blob.
    let revokedInClickTick: number | null = null
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {
      queueMicrotask(() => {
        revokedInClickTick = vi.mocked(URL.revokeObjectURL).mock.calls.length
      })
    })
    fireEvent.click(screen.getByRole('button', { name: 'Download' }))
    await waitFor(() => expect(click).toHaveBeenCalled())
    const dl = calls.find((c) => c.url.includes('download=true'))
    expect(dl?.headers.get('X-CSRF-Token')).toBe('tok-1')
    expect(URL.createObjectURL).toHaveBeenCalled()
    await waitFor(() => expect(revokedInClickTick).toBe(0))
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:x'), { timeout: 3000 })
  })

  it('include switches go into the query', async () => {
    renderPage()
    await screen.findByText('| a | b |')
    fireEvent.click(screen.getByLabelText('Include pending'))
    await waitFor(() => expect(calls.some((c) => c.url.includes('include_pending=true'))).toBe(true))
  })
})
