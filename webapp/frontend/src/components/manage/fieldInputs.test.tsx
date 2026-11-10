import { MantineProvider } from '@mantine/core'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Meta } from '../../api/types'
import { FieldInput } from './fieldInputs'

const meta = { labels: {}, stride: {}, linddun: [] } as unknown as Meta

describe('FieldInput', () => {
  it('the elements input says the IDs come from the C4 model', () => {
    render(
      <MantineProvider>
        <FieldInput field="elements" meta={meta} value={['C2']} required={false} disabled={false} onChange={() => {}} />
      </MantineProvider>,
    )
    expect(screen.getByText('Item and path IDs from the approved C4 model, such as C2, K1 or R1.')).toBeInTheDocument()
  })
})
