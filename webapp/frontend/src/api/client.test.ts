import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiGet, apiPath, apiPost, initCsrf, setCsrf } from './client'

function reply(status: number, body: unknown = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function headerOf(call: unknown[], name: string): string | null {
  const init = call[1] as RequestInit
  return new Headers(init.headers).get(name)
}

describe('client', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    setCsrf('tok-1')
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends the CSRF token and same-origin credentials on apiGet', async () => {
    fetchMock.mockResolvedValue(reply(200, { ok: 1 }))
    await expect(apiGet('/api/meta')).resolves.toEqual({ ok: 1 })
    const call = fetchMock.mock.calls[0]
    expect(call[0]).toBe('/api/meta')
    expect(headerOf(call, 'X-CSRF-Token')).toBe('tok-1')
    expect((call[1] as RequestInit).credentials).toBe('same-origin')
  })

  it('sends JSON, the CSRF token, and same-origin credentials on apiPost', async () => {
    fetchMock.mockResolvedValue(reply(200, { risk: {} }))
    await apiPost('/api/main/systems/s/risks', { fields: { title: 'x' } })
    const call = fetchMock.mock.calls[0]
    const init = call[1] as RequestInit
    expect(init.method).toBe('POST')
    expect(headerOf(call, 'X-CSRF-Token')).toBe('tok-1')
    expect(headerOf(call, 'Content-Type')).toBe('application/json')
    expect(init.credentials).toBe('same-origin')
    expect(JSON.parse(init.body as string)).toEqual({ fields: { title: 'x' } })
  })

  it('rejects a 401 with an ApiError carrying the status and detail', async () => {
    fetchMock.mockResolvedValue(reply(401, { detail: 'signed out' }))
    const err = (await apiGet('/api/session').catch((e: unknown) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(401)
    expect(err.detail).toBe('signed out')
  })

  it('keeps the body of a 409 for the caller', async () => {
    fetchMock.mockResolvedValue(reply(409, { detail: 'stale', current: { id: 'T1' } }))
    const err = (await apiPost('/x', {}).catch((e: unknown) => e)) as ApiError
    expect(err.status).toBe(409)
    expect(err.body).toEqual({ detail: 'stale', current: { id: 'T1' } })
  })

  it('encodes each part of an API path', () => {
    expect(apiPath('main', 'a b', 'risks', 'T/1')).toBe('/api/main/systems/a%20b/risks/T%2F1')
    expect(apiPath('trial', 'x')).toBe('/api/trial/systems/x')
  })
})

describe('initCsrf', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    localStorage.clear()
    history.replaceState(null, '', '/')
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    history.replaceState(null, '', '/')
  })

  it('stores a new token, strips the fragment, and uses the token', async () => {
    history.replaceState(null, '', '/register?a=1#k=fresh')
    fetchMock.mockResolvedValue(reply(200, {}))
    await initCsrf()
    expect(localStorage.getItem('tmweb.k')).toBe('fresh')
    expect(location.hash).toBe('')
    expect(location.pathname + location.search).toBe('/register?a=1')
    expect(fetchMock).not.toHaveBeenCalled()
    await apiGet('/api/meta')
    expect(headerOf(fetchMock.mock.calls[0], 'X-CSRF-Token')).toBe('fresh')
  })

  it('keeps the old token when a different one fails verification', async () => {
    localStorage.setItem('tmweb.k', 'good')
    history.replaceState(null, '', '/#k=junk')
    fetchMock.mockResolvedValueOnce(reply(401, { detail: 'signed out' }))
    await initCsrf()
    expect(headerOf(fetchMock.mock.calls[0], 'X-CSRF-Token')).toBe('junk')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/session')
    expect(localStorage.getItem('tmweb.k')).toBe('good')
    expect(location.hash).toBe('')
    fetchMock.mockResolvedValueOnce(reply(200, {}))
    await apiGet('/api/meta')
    expect(headerOf(fetchMock.mock.calls[1], 'X-CSRF-Token')).toBe('good')
  })

  it('replaces the old token when the new one verifies', async () => {
    localStorage.setItem('tmweb.k', 'old')
    history.replaceState(null, '', '/#k=new')
    fetchMock.mockResolvedValueOnce(reply(200, { reviewer: 'r', trial: false }))
    await initCsrf()
    expect(localStorage.getItem('tmweb.k')).toBe('new')
    fetchMock.mockResolvedValueOnce(reply(200, {}))
    await apiGet('/api/meta')
    expect(headerOf(fetchMock.mock.calls[1], 'X-CSRF-Token')).toBe('new')
  })

  it('uses the stored token when there is no fragment', async () => {
    localStorage.setItem('tmweb.k', 'kept')
    await initCsrf()
    fetchMock.mockResolvedValueOnce(reply(200, {}))
    await apiGet('/api/meta')
    expect(headerOf(fetchMock.mock.calls[0], 'X-CSRF-Token')).toBe('kept')
  })
})
