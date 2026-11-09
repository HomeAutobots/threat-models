import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
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
  return render(
    <MantineProvider>
      <QueryClientProvider client={makeQueryClient()}>
        <RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />
      </QueryClientProvider>
    </MantineProvider>,
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
})
