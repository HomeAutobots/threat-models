import { MantineProvider } from '@mantine/core'
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Change, Meta, Risk, RiskDetail } from '../../api/types'
import { cited, item, modelInfo, RECORD } from '../../test-c4'
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
  elements: ['C2', 'R1'],
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


function detail(over: Partial<RiskDetail> = {}, riskOver: Partial<Risk> = {}): RiskDetail {
  return {
    risk: { ...risk, ...riskOver },
    elements: {
      C2: cited('same', RECORD.items.C2),
      R1: cited('same', RECORD.rels.R1),
    },
    model: modelInfo(),
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

  it('shows the cited items under the caption', () => {
    renderRecord(detail())
    const w = within(card('where'))
    // The caption shows once, in the heading.
    expect(w.getAllByText(/From MODEL-1 \(current\)/)).toHaveLength(1)
    expect(w.getByText('C1 \u2192 C2')).toBeInTheDocument()
    expect(w.getByText('Orders API')).toBeInTheDocument()
    expect(w.getByText('S1 \u203a C2')).toBeInTheDocument()
  })

  it('a changed item shows As written and Now, and the caption says the model moved on', () => {
    renderRecord(
      detail({
        model: modelInfo({ latest_id: 'MODEL-2', moved_on: true, changed: ['C2'] }),
        elements: {
          C2: cited('changed', RECORD.items.C2, item({ ...RECORD.items.C2, name: 'Orders service' })),
          R1: cited('same', RECORD.rels.R1),
        },
      }),
    )
    const w = within(card('where'))
    expect(w.getAllByText(/Written against MODEL-1; the latest is MODEL-2/)).toHaveLength(1)
    expect(w.getByText('Orders API')).toBeInTheDocument()
    expect(w.getByText('Orders service')).toBeInTheDocument()
    expect(w.getAllByText('As written')).toHaveLength(1)
  })

  it('a DFD-era risk says its IDs are as written', () => {
    renderRecord(
      detail({
        model: modelInfo({ basis: 'dfd', written_against: null }),
        elements: { C2: cited('dfd', null), R1: cited('dfd', null) },
      }),
    )
    expect(within(card('where')).getAllByText(/Written before the C4 model; IDs as written\./)).toHaveLength(1)
  })

  it('the cited items are hidden while the record reloads', () => {
    render(
      <MantineProvider>
        <RiskRecord detail={detail()} meta={meta} history={history} reloading />
      </MantineProvider>,
    )
    expect(within(card('where')).queryByText('Orders API')).toBeNull()
  })

  it.each([
    ['pending', null, 'None (new draft)'],
    ['approved', null, 'None (no re-review pending)'],
    ['rejected', null, 'None (no re-review pending)'],
  ])('last_approved null on a %s risk reads %s', (state, _v, text) => {
    renderRecord(detail({}, { review_state: state, last_approved: null }))
    expect(within(card('record')).getByText(text)).toBeInTheDocument()
  })

  it('last_approved with a value keeps its copy', () => {
    renderRecord(detail({}, { review_state: 'pending', last_approved: { title: 'x' } as never }))
    expect(within(card('record')).getByText('Kept while this re-review is pending')).toBeInTheDocument()
  })

  it('category label', () => {
    renderRecord(detail())
    expect(within(card('glance')).getByText('Information disclosure (STRIDE I)')).toBeInTheDocument()
  })

  it('shows the duplicate comparison only when set', () => {
    const { unmount } = renderRecord(detail())
    expect(document.getElementById('dup')).toBeNull()
    unmount()
    const dup = { ...risk, id: 'T-33', title: 'Other title', elements: ['C2', 'R1', 'K1'] }
    renderRecord(detail({ duplicate: dup }, { possible_duplicate_of: 'T-33' }))
    const d = card('dup')
    expect(within(d).getByText('Other title')).toBeInTheDocument()
    expect(within(d).getByText('C2; R1; K1')).toBeInTheDocument()
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
