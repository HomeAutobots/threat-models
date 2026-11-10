import { MantineProvider } from '@mantine/core'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ModelStatus } from './ModelStatus'

const wrap = (ui: React.ReactNode) => render(<MantineProvider>{ui}</MantineProvider>)

describe('ModelStatus', () => {
  it('shows the state, version and escaped approvals', () => {
    wrap(
      <ModelStatus
        state="changed"
        latest={{ id: 'MODEL-1', version: '2.0', sha256: 'a', ids: {}, approved_by: 'human:ann', approved_at: null, note: 'n‮x' }}
        approvals={[{ id: 'MODEL-1', version: '2.0', sha256: 'a', ids: {}, approved_by: 'human:ann', approved_at: null, note: 'n‮x' }]}
      />,
    )
    expect(screen.getByText('changed')).toBeInTheDocument()
    expect(screen.getByText('Approved version 2.0')).toBeInTheDocument()
    expect(screen.getByText('n\\u202ex')).toBeInTheDocument()
  })

  it('renders no table without approvals', () => {
    wrap(<ModelStatus state="none" latest={null} approvals={[]} />)
    expect(screen.queryByRole('table')).toBeNull()
  })
})
