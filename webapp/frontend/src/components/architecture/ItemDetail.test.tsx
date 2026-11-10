import { MantineProvider } from '@mantine/core'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { RECORD, risk } from '../../test-c4'
import { ItemDetail } from './ItemDetail'

describe('ItemDetail', () => {
  it('shows the record, descendants risks and path risks, and links to the risk', () => {
    render(
      <MantineProvider>
        <MemoryRouter>
          <ItemDetail reg="main" slug="demo" id="C2" record={RECORD} risks={[risk('RISK-1', ['C2'], { status: 'mitigated' }), risk('RISK-2', ['K1']), risk('RISK-3', ['R1']), risk('RISK-4', ['A1'])]} />
        </MemoryRouter>
      </MantineProvider>,
    )
    expect(screen.getByText('Python')).toBeInTheDocument()
    expect(screen.getByText('S1 › C2')).toBeInTheDocument()
    expect(screen.getByText(/Title RISK-1.*mitigated/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'RISK-1' })).toHaveAttribute('href', '/main/demo/risks/RISK-1')
    expect(screen.getByRole('link', { name: 'RISK-2' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'RISK-3' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'RISK-4' })).toBeNull()
  })

  it('shows no risk headings when no risk cites it', () => {
    render(
      <MantineProvider>
        <MemoryRouter>
          <ItemDetail reg="main" slug="demo" id="N1" record={RECORD} risks={[]} />
        </MemoryRouter>
      </MantineProvider>,
    )
    expect(screen.queryByText(/^Risks on/)).toBeNull()
  })
})
