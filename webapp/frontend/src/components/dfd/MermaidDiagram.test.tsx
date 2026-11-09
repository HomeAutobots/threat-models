import { MantineProvider } from '@mantine/core'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const initialize = vi.fn()
const renderFn = vi.fn()
vi.mock('mermaid', () => ({ default: { initialize, render: renderFn } }))

import { MermaidDiagram } from './MermaidDiagram'

beforeEach(() => {
  initialize.mockReset()
  renderFn.mockReset()
})

describe('MermaidDiagram', () => {
  it('initializes mermaid in strict mode without startOnLoad, then renders', async () => {
    renderFn.mockResolvedValue({ svg: '<svg data-testid="out"></svg>' })
    render(
      <MantineProvider>
        <MermaidDiagram source="graph TD; A-->B" />
      </MantineProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('out')).toBeInTheDocument())
    expect(initialize).toHaveBeenCalledWith({ startOnLoad: false, securityLevel: 'strict' })
    expect(renderFn.mock.calls[0][1]).toBe('graph TD; A-->B')
  })

  it('on error shows the source and the error', async () => {
    renderFn.mockRejectedValue(new Error('bad syntax'))
    render(
      <MantineProvider>
        <MermaidDiagram source="not a diagram" />
      </MantineProvider>,
    )
    expect(await screen.findByText(/bad syntax/)).toBeInTheDocument()
    expect(screen.getByText('not a diagram')).toBeInTheDocument()
  })

  it('on error shows the source and the error with invisible and control characters escaped', async () => {
    renderFn.mockRejectedValue(new Error('bad \u202esyntax'))
    render(
      <MantineProvider>
        <MermaidDiagram source={'graph TD; A-->B\u200b\u001b'} />
      </MantineProvider>,
    )
    expect(await screen.findByText('Diagram error: bad \\u202esyntax')).toBeInTheDocument()
    expect(screen.getByText('graph TD; A-->B\\u200b\\x1b')).toBeInTheDocument()
  })
})
