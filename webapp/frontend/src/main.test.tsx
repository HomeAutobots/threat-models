import { beforeEach, describe, expect, it, vi } from 'vitest'

const render = vi.fn()

vi.mock('react-dom/client', () => ({ createRoot: () => ({ render }) }))
vi.mock('./api/client', () => ({ initCsrf: () => Promise.reject(new Error('storage blocked')) }))
vi.mock('./routes', () => ({ routes: [] }))
vi.mock('react-router', () => ({ createBrowserRouter: () => ({}), RouterProvider: () => null }))

describe('main', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="root"></div>'
    render.mockClear()
  })

  it('still renders the app when initCsrf rejects', async () => {
    await import('./main')
    await vi.waitFor(() => expect(render).toHaveBeenCalledTimes(1))
  })
})
