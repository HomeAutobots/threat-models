import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// jsdom lacks these browser APIs, which Mantine uses.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
})

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
class IntersectionObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return []
  }
}
// Plain assignment, so a test's vi.unstubAllGlobals() does not remove them.
globalThis.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver
globalThis.IntersectionObserver = IntersectionObserverMock as unknown as typeof IntersectionObserver
window.HTMLElement.prototype.scrollIntoView = vi.fn()
// Mantine's autosizing Textarea listens for font loading.
if (!('fonts' in document)) {
  Object.defineProperty(document, 'fonts', {
    value: { addEventListener() {}, removeEventListener() {} },
  })
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  localStorage.clear()
})
