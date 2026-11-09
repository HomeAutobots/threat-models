import { MantineProvider } from '@mantine/core'
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Change, DfdInfo, Meta, Risk, RiskDetail } from '../../api/types'
import { RiskRecord } from './RiskRecord'

const meta = {
  fields: [],
  editable: [],
  labels: {},
  stride: { I: 'Information disclosure' },
  linddun: [],
  statuses: [],
} as unknown as Meta

const risk: Risk = {
  id: 'T-37',
  title: 'Retrieval cache serves one order summary to another customer',
  elements: ['P7', 'F19'],
  category: 'I',
  method: 'STRIDE per element',
  origin: 'threat-model',
  origin_ref: 'run 20261107-01',
  description: 'P7 caches order summaries in a shared retrieval cache.',
  attack_scenario: 'A customer replays an older conversation ID.',
  attack_path: 'E1 to P2 to P7',
  impact: 'Disclosure of PII',
  impact_rating: 'High',
  likelihood: 'Medium',
  likelihood_rationale: 'IDs appear in shared links',
  score: '6',
  score_method: 'likelihood x impact',
  assumptions: 'Cache is in process memory',
  implemented_controls: 'None identified',
  recommended_controls: 'Key the cache by customer ID',
  control_refs: null,
  exception_ref: null,
  treatment: 'Mitigate',
  decision_requested: '',
  evidence: 'dfd.md v1.0',
  ai_confidence: 'medium',
  owner: null,
  due: null,
  status: 'Open',
  status_reason: null,
  test: 'a test',
  ticket: 'TK-1',
  notes: 'a note',
  review_state: 'pending',
  last_approved: null,
  drafted_by: 'ai:20261107-01',
  reviewed_by: null,
  reviewed_at: null,
  review_note: null,
  possible_duplicate_of: null,
  merged_into: null,
  dfd_approval_id: 'DFD-1',
  detail_complete: true,
  created_at: '2026-11-07T10:12:00',
  updated_at: '2026-11-07T10:12:00',
}

const dfd: DfdInfo = { state: 'current', latest_id: 'DFD-1', written_against: 'DFD-1', error: null }

function detail(over: Partial<RiskDetail> = {}, riskOver: Partial<Risk> = {}): RiskDetail {
  return {
    risk: { ...risk, ...riskOver },
    elements: {
      P7: { name: 'Support assistant', type: 'process', description: 'LLM chat' },
      F19: { name: 'Order lookups', type: 'flow', from: 'P7', to: 'P3', description: 'scoped' },
    },
    dfd,
    editors_since_approval: [],
    duplicate: null,
    ...over,
  }
}

const history: Change[] = []

function renderRecord(d: RiskDetail, h: Change[] = history) {
  return render(
    <MantineProvider>
      <RiskRecord detail={d} meta={meta} history={h} />
    </MantineProvider>,
  )
}

const card = (id: string) => document.getElementById(id) as HTMLElement
const count = (el: HTMLElement) => within(el).queryAllByText('Not provided').length

describe('RiskRecord', () => {
  it('empty fields say Not provided', () => {
    renderRecord(detail())
    expect(count(card('controls'))).toBe(1)
    expect(count(card('treatment'))).toBe(5)
  })

  it('shows a 5000-character field in full', () => {
    const long = 'x'.repeat(5000)
    const { container } = renderRecord(detail({}, { description: long }))
    expect(card('threat').textContent).toContain(long)
    for (const el of container.querySelectorAll<HTMLElement>('*')) {
      expect(el.style.textOverflow).toBe('')
      expect(el.style.webkitLineClamp).toBeFalsy()
      expect(el.getAttribute('style') ?? '').not.toMatch(/line-clamp|text-overflow/)
    }
  })

  it('renders hostile text literally', () => {
    const hostile = '<img src=x onerror=alert(1)> ‮'
    const { container } = renderRecord(detail({}, { description: hostile }))
    expect(container.querySelector('img')).toBeNull()
    const text = card('threat').textContent ?? ''
    expect(text).toContain('<img src=x onerror=alert(1)>')
    expect(text).toContain('\\u202e')
    expect(text).not.toContain('‮')
  })

  it('element source label: current', () => {
    renderRecord(detail())
    expect(within(card('where')).getByText('From DFD-1 (current)')).toBeInTheDocument()
    expect(within(card('where')).getByText('P7 → P3')).toBeInTheDocument()
  })

  it('element source label: changed, with an element missing', () => {
    renderRecord(
      detail({
        dfd: { state: 'changed', latest_id: 'DFD-2', written_against: 'DFD-1', error: null },
        elements: { P7: null, F19: null },
      }),
    )
    const where = card('where')
    expect(
      within(where).getByText(
        'From the current dfd.md, which has changed since this risk was written against DFD-1',
      ),
    ).toBeInTheDocument()
    expect(within(where).getAllByText('Not in the current DFD')).toHaveLength(2)
  })

  it('element source label: error', () => {
    renderRecord(
      detail({ dfd: { state: 'none', latest_id: null, written_against: null, error: 'bad file' }, elements: {} }),
    )
    expect(within(card('where')).getByText('DFD details unavailable: bad file')).toBeInTheDocument()
  })

  it('category label', () => {
    renderRecord(detail())
    expect(within(card('glance')).getByText('Information disclosure (STRIDE I)')).toBeInTheDocument()
  })

  it('shows the duplicate comparison only when set', () => {
    const { unmount } = renderRecord(detail())
    expect(document.getElementById('dup')).toBeNull()
    unmount()
    const dup = { ...risk, id: 'T-33', title: 'Other title', elements: ['P7', 'F19', 'F18'] }
    renderRecord(detail({ duplicate: dup }, { possible_duplicate_of: 'T-33' }))
    const d = card('dup')
    expect(within(d).getByText('Other title')).toBeInTheDocument()
    expect(within(d).getByText('P7; F19; F18')).toBeInTheDocument()
  })

  it('header badges and history table', () => {
    const h: Change[] = [
      { seq: 52, at: '2026-11-07T10:12:00', op: 'add', tbl: 'risks', row_key: 'T-37', actor: 'ai:20261107-01', diff: {}, note: '', prev_hash: '', hash: '' },
    ]
    renderRecord(detail(), h)
    expect(screen.getByText('New draft')).toBeInTheDocument()
    expect(screen.getByText('AI confidence: medium')).toBeInTheDocument()
    const rec = card('record')
    expect(within(rec).getByText('52')).toBeInTheDocument()
    expect(within(rec).getAllByText('AI, run 20261107-01').length).toBeGreaterThan(0)
  })
})
