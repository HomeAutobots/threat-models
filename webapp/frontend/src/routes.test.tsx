import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient } from './api/queries'
import { routes } from './routes'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderApp(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(
    <MantineProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </MantineProvider>,
  )
  return router
}

function systemsApi(systems: Record<string, string[]>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url === '/api/session') return json({ reviewer: 'Sam', trial: true })
      const m = url.match(/^\/api\/(\w+)\/systems$/)
      if (m) return json((systems[m[1]] ?? []).map((slug) => ({ slug, name: slug, created_at: 'x' })))
      return json([])
    }),
  )
}

describe('app', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('401 shows the signed-out screen', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ detail: 'signed out' }, 401)))
    renderApp('/')
    expect(await screen.findByText('Signed out')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Open the sign-in link shown in the Terminal window that started the app. ' +
          'If that window is closed, start the app again for a new link.',
      ),
    ).toBeInTheDocument()
  })

  it('says so when there are no systems', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        url === '/api/session' ? json({ reviewer: 'Sam', trial: false }) : json([]),
      ),
    )
    renderApp('/')
    expect(
      await screen.findByText('No systems yet. Create one in the terminal with ./tmreg init-system.'),
    ).toBeInTheDocument()
  })

  it('/trial (the Trial switch on Home) opens the trial register\'s first system', async () => {
    systemsApi({ main: ['real'], trial: ['practice', 'other'] })
    const router = renderApp('/trial')
    await waitFor(() => expect(router.state.location.pathname).toBe('/trial/practice/register'))
  })

  it('/main opens the main register\'s first system', async () => {
    systemsApi({ main: ['real'], trial: ['practice'] })
    const router = renderApp('/main')
    await waitFor(() => expect(router.state.location.pathname).toBe('/main/real/register'))
  })

  it('/trial with no systems says so, under the trial banner', async () => {
    systemsApi({ main: ['real'] })
    const router = renderApp('/trial')
    expect(
      await screen.findByText('No systems yet. Create one in the terminal with ./tmreg init-system.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Trial register: practice data, not the real register')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/trial')
  })

  it('an unknown register goes home', async () => {
    systemsApi({ main: ['real'] })
    const router = renderApp('/bogus')
    await waitFor(() => expect(router.state.location.pathname).toBe('/main/real/register'))
  })
})
