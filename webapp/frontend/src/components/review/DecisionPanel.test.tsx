import { MantineProvider } from '@mantine/core'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DecisionPanel } from './DecisionPanel'

const NOTE = 'x'.repeat(20)

function baseProps() {
  return {
    riskId: 'T-37',
    isReReview: false,
    duplicateId: null as string | null,
    noteMin: 20,
    busy: false,
    error: null as string | null,
    note: '',
    onNote: vi.fn(),
    onApprove: vi.fn(),
    onReject: vi.fn(),
    onMerge: vi.fn(),
    onEdit: vi.fn(),
  }
}

function renderPanel(over: Partial<Parameters<typeof DecisionPanel>[0]> = {}) {
  const props = {
    riskId: 'T-37',
    isReReview: false,
    duplicateId: 'T-33' as string | null,
    noteMin: 20,
    busy: false,
    error: null as string | null,
    note: '',
    onNote: vi.fn(),
    onApprove: vi.fn(),
    onReject: vi.fn(),
    onMerge: vi.fn(),
    onEdit: vi.fn(),
    ...over,
  }
  render(
    <MantineProvider>
      <DecisionPanel {...props} />
    </MantineProvider>,
  )
  return props
}

describe('DecisionPanel', () => {
  it('approve enables at the minimum', () => {
    renderPanel({ note: 'x'.repeat(19) })
    expect(screen.getByRole('button', { name: 'Approve T-37' })).toBeDisabled()
    expect(screen.getByText('19 / 20')).toBeInTheDocument()
  })

  it('counts the note in code points, as core does', () => {
    renderPanel({ note: '😀'.repeat(20) })
    expect(screen.getByText('20 / 20')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve T-37' })).toBeEnabled()
  })

  it('approve calls onApprove at exactly the minimum', () => {
    const p = renderPanel({ note: NOTE })
    const approve = screen.getByRole('button', { name: 'Approve T-37' })
    expect(approve).toBeEnabled()
    fireEvent.click(approve)
    expect(p.onApprove).toHaveBeenCalledTimes(1)
  })

  it('counts the note as the core does, without outer spaces', () => {
    renderPanel({ note: `  ${'x'.repeat(19)}  ` })
    expect(screen.getByRole('button', { name: 'Approve T-37' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Reject T-37' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Merge into T-33' })).toBeDisabled()
  })

  it('shows a Trial register badge only in trial', () => {
    const { unmount } = render(<MantineProvider><DecisionPanel {...baseProps()} trial /></MantineProvider>)
    expect(screen.getByText('Trial register')).toBeInTheDocument()
    unmount()
    render(<MantineProvider><DecisionPanel {...baseProps()} /></MantineProvider>)
    expect(screen.queryByText('Trial register')).not.toBeInTheDocument()
  })

  it('re-review labels', () => {
    renderPanel({ isReReview: true })
    expect(screen.getByRole('button', { name: 'Reject and restore last approved' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Merge/ })).not.toBeInTheDocument()
  })

  it('has no merge button without a duplicate', () => {
    renderPanel({ duplicateId: null })
    expect(screen.queryByRole('button', { name: /Merge/ })).not.toBeInTheDocument()
  })

  it('busy disables every button', () => {
    renderPanel({ note: NOTE, busy: true })
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBe(4)
    for (const b of buttons) expect(b).toBeDisabled()
  })

  it('shows the error and the fixed copy', () => {
    renderPanel({ error: 'Note too short for core' })
    expect(screen.getByRole('alert')).toHaveTextContent('Note too short for core')
    expect(
      screen.getByText(
        'You approve exactly the version on this page. If it changes while you read, nothing is saved and the new version is shown.',
      ),
    ).toBeInTheDocument()
  })

  it('passes typing and clicks through', () => {
    const p = renderPanel({ note: NOTE })
    fireEvent.change(screen.getByLabelText('Review note'), { target: { value: 'abc' } })
    expect(p.onNote).toHaveBeenCalledWith('abc')
    fireEvent.click(screen.getByRole('button', { name: 'Reject T-37' }))
    fireEvent.click(screen.getByRole('button', { name: 'Merge into T-33' }))
    fireEvent.click(screen.getByRole('button', { name: 'Edit before deciding' }))
    expect(p.onReject).toHaveBeenCalledTimes(1)
    expect(p.onMerge).toHaveBeenCalledTimes(1)
    expect(p.onEdit).toHaveBeenCalledTimes(1)
  })
})
