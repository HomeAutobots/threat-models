import type { Reg } from './types'

const STORAGE_KEY = 'tmweb.k'
const HEADER = 'X-CSRF-Token'

let csrf = ''

export class ApiError extends Error {
  status: number
  detail: string
  body: unknown

  constructor(status: number, detail: string, body: unknown) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.body = body
  }
}

export function setCsrf(token: string): void {
  csrf = token
}

function readStored(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function writeStored(token: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, token)
  } catch {
    // Storage may be blocked; the token then lasts for this page only.
  }
}

async function accepted(token: string): Promise<boolean> {
  try {
    const response = await fetch('/api/session', {
      credentials: 'same-origin',
      headers: { [HEADER]: token },
    })
    return response.status === 200
  } catch {
    return false
  }
}

/**
 * Take the token from the sign-in redirect (`/#k=<token>`), keep it in localStorage, and remove it
 * from the address bar. A token that differs from a stored one replaces it only if the server
 * accepts it, so a page that sends the browser to `/#k=<junk>` cannot sign the owner out.
 */
export async function initCsrf(): Promise<void> {
  const fresh = new URLSearchParams(location.hash.replace(/^#/, '')).get('k')
  const stored = readStored()
  if (fresh !== null) {
    history.replaceState(null, '', location.pathname + location.search)
  }
  if (fresh && fresh !== stored) {
    if (!stored || (await accepted(fresh))) {
      writeStored(fresh)
      csrf = fresh
      return
    }
  }
  if (stored) csrf = stored
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set(HEADER, csrf)
  const response = await fetch(path, { ...init, headers, credentials: 'same-origin' })
  const text = await response.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = text
    }
  }
  if (!response.ok) {
    const detail =
      body && typeof body === 'object' && typeof (body as { detail?: unknown }).detail === 'string'
        ? (body as { detail: string }).detail
        : response.statusText || `HTTP ${response.status}`
    throw new ApiError(response.status, detail, body)
  }
  return body as T
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'GET' })
}

/** Like `apiGet`, but returns the raw response text (reports are not JSON). */
export async function apiGetText(path: string): Promise<string> {
  const headers = new Headers()
  headers.set(HEADER, csrf)
  const response = await fetch(path, { method: 'GET', headers, credentials: 'same-origin' })
  const text = await response.text()
  if (!response.ok) {
    let body: unknown = text
    let detail = response.statusText || `HTTP ${response.status}`
    try {
      body = JSON.parse(text)
      const d = (body as { detail?: unknown } | null)?.detail
      if (typeof d === 'string') detail = d
    } catch {
      // Not JSON; keep the status text.
    }
    throw new ApiError(response.status, detail, body)
  }
  return text
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function apiPath(reg: Reg, slug: string, ...parts: string[]): string {
  return ['/api', reg, 'systems', ...[slug, ...parts].map(encodeURIComponent)].join('/')
}
