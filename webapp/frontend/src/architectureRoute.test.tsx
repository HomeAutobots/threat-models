import { render, screen } from '@testing-library/react'
import { MemoryRouter, Navigate, Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'
import { routes } from './routes'

describe('architecture route', () => {
  const system = routes[0].children!.find((r) => r.path === ':reg/:slug')!
  const find = (path: string) => system.children!.find((r) => r.path === path)

  it('serves the Architecture page and redirects dfd to it', () => {
    expect(find('architecture')).toBeDefined()
    const dfd = find('dfd')!
    expect((dfd.element as { type: unknown }).type).toBe(Navigate)
    render(
      <MemoryRouter initialEntries={['/main/demo/dfd']}>
        <Routes>
          <Route path=":reg/:slug">
            <Route path="architecture" element={<p>ARCH PAGE</p>} />
            <Route path="dfd" element={dfd.element} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByText('ARCH PAGE')).toBeInTheDocument()
  })
})
