import { MantineProvider } from '@mantine/core'
import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SectionOutline } from './SectionOutline'

describe('SectionOutline', () => {
  const original = globalThis.IntersectionObserver
  afterEach(() => {
    globalThis.IntersectionObserver = original
  })

  it('fills a dot when its card intersects and keeps it filled', () => {
    let callback: IntersectionObserverCallback = () => {}
    class IO {
      constructor(cb: IntersectionObserverCallback) {
        callback = cb
      }
      observe = vi.fn()
      unobserve = vi.fn()
      disconnect = vi.fn()
      takeRecords = () => []
    }
    globalThis.IntersectionObserver = IO as unknown as typeof IntersectionObserver
    document.body.insertAdjacentHTML('beforeend', '<section id="glance"></section><section id="where"></section>')
    render(
      <MantineProvider>
        <SectionOutline
          sections={[
            { id: 'glance', n: 1, title: 'At a glance' },
            { id: 'where', n: 2, title: 'Where it happens' },
          ]}
        />
      </MantineProvider>,
    )
    const fire = (id: string, isIntersecting: boolean) =>
      act(() => {
        callback([{ target: document.getElementById(id), isIntersecting } as unknown as IntersectionObserverEntry], {} as IntersectionObserver)
      })
    expect(screen.getByTestId('dot-glance')).toHaveAttribute('data-seen', 'false')
    fire('glance', true)
    expect(screen.getByTestId('dot-glance')).toHaveAttribute('data-seen', 'true')
    fire('glance', false)
    expect(screen.getByTestId('dot-glance')).toHaveAttribute('data-seen', 'true')
    expect(screen.getByTestId('dot-where')).toHaveAttribute('data-seen', 'false')
    document.getElementById('glance')?.remove()
    document.getElementById('where')?.remove()
  })
})
