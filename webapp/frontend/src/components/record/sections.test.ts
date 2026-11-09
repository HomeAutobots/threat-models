import { describe, expect, it } from 'vitest'
import { SECTIONS } from './sections'

// Copied from registry/tmreg/model.py RISK_FIELDS.
const RISK_FIELDS = [
  'id', 'title', 'elements', 'category', 'method', 'origin', 'origin_ref', 'description',
  'attack_scenario', 'attack_path', 'impact', 'impact_rating', 'likelihood',
  'likelihood_rationale', 'score', 'score_method', 'assumptions', 'implemented_controls',
  'recommended_controls', 'control_refs', 'exception_ref', 'treatment', 'decision_requested',
  'evidence', 'ai_confidence', 'owner', 'due', 'status', 'status_reason', 'test', 'ticket',
  'notes', 'review_state', 'last_approved', 'drafted_by', 'reviewed_by', 'reviewed_at',
  'review_note', 'possible_duplicate_of', 'merged_into', 'dfd_approval_id', 'detail_complete',
  'created_at', 'updated_at',
]

describe('SECTIONS', () => {
  it('every field is covered', () => {
    const covered = new Set(SECTIONS.flatMap((s) => s.fields))
    const expected = new Set(RISK_FIELDS.filter((f) => f !== 'id' && f !== 'title'))
    expect(covered).toEqual(expected)
  })

  it('has nine numbered sections in order', () => {
    expect(SECTIONS.map((s) => [s.n, s.id])).toEqual([
      [1, 'glance'], [2, 'where'], [3, 'threat'], [4, 'impact'], [5, 'controls'],
      [6, 'treatment'], [7, 'evidence'], [8, 'dup'], [9, 'record'],
    ])
  })
})
