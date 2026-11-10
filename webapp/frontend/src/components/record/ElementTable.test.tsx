import { MantineProvider } from '@mantine/core'
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { cited, item, modelInfo, RECORD, rel } from '../../test-c4'
import type { CitedItem, ModelInfo } from '../../api/types'
import { ElementTable, elementCaption } from './ElementTable'

function renderTable(ids: string[], elements: Record<string, CitedItem>, model: ModelInfo = modelInfo()) {
  return render(
    <MantineProvider>
      <ElementTable ids={ids} elements={elements} model={model} />
    </MantineProvider>,
  )
}

const row = (id: string) => screen.getByText(id).closest('tr') as HTMLElement

describe('ElementTable', () => {
  it('shows an item: kind, where, name, technology, description and DFD role', () => {
    renderTable(['K1'], { K1: cited('same', item({ kind: 'component', name: 'Cart', role: 'Process', technology: 'Python', description: 'Holds the basket', where: ['S1', 'C2', 'K1'] })) })
    const r = within(row('K1'))
    expect(r.getByText('component')).toBeInTheDocument()
    expect(r.getByText('S1 › C2 › K1')).toBeInTheDocument()
    expect(r.getByText('Cart')).toBeInTheDocument()
    expect(r.getByText('Python')).toBeInTheDocument()
    expect(r.getByText('Holds the basket')).toBeInTheDocument()
    expect(r.getByText('Process')).toBeInTheDocument()
    expect(r.queryByText('As written')).toBeNull()
  })

  it('shows a path: from to, data sent and returned, auth, and crossings per environment', () => {
    renderTable(['R1'], { R1: cited('same', RECORD.rels.R1) })
    const r = within(row('R1'))
    expect(r.getByText('C1 → C2')).toBeInTheDocument()
    expect(r.getByText('order')).toBeInTheDocument()
    expect(r.getByText('receipt')).toBeInTheDocument()
    expect(r.getByText('OAuth token')).toBeInTheDocument()
    expect(r.getByText('ENV1: TB1, TB2')).toBeInTheDocument()
    expect(r.getByText('Places orders')).toBeInTheDocument()
    expect(r.getByText('Data flow')).toBeInTheDocument()
  })

  it('a changed path shows both versions, labelled As written and Now', () => {
    const latest = rel({ ...RECORD.rels.R1, destination: 'C3', properties: { 'tm.data.sent': 'order v2', 'tm.auth': 'mTLS' }, crossings: { ENV1: ['TB1'] } })
    renderTable(['R1'], { R1: cited('changed', RECORD.rels.R1, latest) }, modelInfo({ latest_id: 'MODEL-2', moved_on: true, changed: ['R1'] }))
    const r = within(row('R1'))
    expect(r.getByText('As written')).toBeInTheDocument()
    expect(r.getByText('Now')).toBeInTheDocument()
    expect(r.getByText('C1 → C2')).toBeInTheDocument()
    expect(r.getByText('C1 → C3')).toBeInTheDocument()
    expect(r.getByText('order')).toBeInTheDocument()
    expect(r.getByText('order v2')).toBeInTheDocument()
    expect(r.getByText('OAuth token')).toBeInTheDocument()
    expect(r.getByText('mTLS')).toBeInTheDocument()
    expect(r.getByText('ENV1: TB1')).toBeInTheDocument()
  })

  it('a removed item shows what was written and says it was removed in the latest model', () => {
    renderTable(['C9'], { C9: cited('removed', item({ name: 'Old queue', where: ['S1', 'C9'] })) }, modelInfo({ latest_id: 'MODEL-2', moved_on: true, changed: ['C9'] }))
    const r = within(row('C9'))
    expect(r.getByText('Old queue')).toBeInTheDocument()
    expect(r.getByText('Removed in MODEL-2')).toBeInTheDocument()
    expect(r.queryByText('Now')).toBeNull()
  })

  it('a dynamic view shows its title and steps', () => {
    renderTable(['SEQ1'], { SEQ1: cited('same', RECORD.views.SEQ1) })
    const r = within(row('SEQ1'))
    expect(r.getByText('Checkout')).toBeInTheDocument()
    expect(r.getByText('R1')).toBeInTheDocument()
  })

  it('a DFD-era risk shows the IDs as written, with the caption once', () => {
    const model = modelInfo({ basis: 'dfd', written_against: null })
    renderTable(['P7', 'F19'], { P7: cited('dfd', null), F19: cited('dfd', null) }, model)
    expect(screen.getByText('P7')).toBeInTheDocument()
    expect(screen.getByText('F19')).toBeInTheDocument()
    expect(elementCaption(model)).toBe('Written before the C4 model; IDs as written.')
    expect(screen.queryByText('Now')).toBeNull()
  })

  it('no IDs says Not provided', () => {
    renderTable([], {})
    expect(screen.getByText('Not provided')).toBeInTheDocument()
  })

  it('renders hostile text literally', () => {
    const { container } = renderTable(['C1'], { C1: cited('same', item({ name: '<img src=x onerror=alert(1)> ‮', description: '<b>x</b>' })) })
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>')
    expect(container.textContent).toContain('\\u202e')
    expect(container.textContent).not.toContain('‮')
  })

  it('captions', () => {
    expect(elementCaption(modelInfo())).toBe('From MODEL-1 (current)')
    expect(elementCaption(modelInfo({ latest_id: 'MODEL-2', moved_on: true }))).toBe('Written against MODEL-1; the latest is MODEL-2')
  })
})
