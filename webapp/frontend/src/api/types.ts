// Shapes of the JSON the back end returns (webapp/backend/tmweb/api_read.py and api_write.py).

export type Reg = 'main' | 'trial'

export interface Session {
  reviewer: string
  trial: boolean
}

export interface Meta {
  fields: string[]
  editable: string[]
  labels: Record<string, string>
  stride: Record<string, string>
  linddun: string[]
  treatments: string[]
  confidence: string[]
  min_lengths: Record<string, number>
  note_min: number
  human_required: string[]
  ai_required: string[]
  statuses: string[]
  origins: string[]
  methods: string[]
}

export interface System {
  slug: string
  name: string
  created_at: string
}

export interface Risk {
  id: string
  title: string | null
  elements: string[] | null
  category: string | null
  method: string | null
  origin: string | null
  origin_ref: string | null
  description: string | null
  attack_scenario: string | null
  attack_path: string | null
  impact: string | null
  impact_rating: string | null
  likelihood: string | null
  likelihood_rationale: string | null
  score: string | null
  score_method: string | null
  assumptions: string | null
  implemented_controls: string | null
  recommended_controls: string | null
  control_refs: string[] | null
  exception_ref: string | null
  treatment: string | null
  decision_requested: string | null
  evidence: string[] | string | null
  ai_confidence: string | null
  owner: string | null
  due: string | null
  status: string | null
  status_reason: string | null
  test: string | null
  ticket: string | null
  notes: string | null
  review_state: 'pending' | 'approved' | 'rejected' | string
  last_approved: Record<string, unknown> | null
  drafted_by: string | null
  reviewed_by: string | null
  reviewed_at: string | null
  review_note: string | null
  possible_duplicate_of: string | null
  merged_into: string | null
  dfd_approval_id: string | null
  detail_complete: boolean | number | null
  created_at: string | null
  updated_at: string | null
  [field: string]: unknown
}

export interface ElementDetail {
  name: string
  type: string
  description?: string
  [key: string]: unknown
}

export type DfdState = 'none' | 'current' | 'changed'

export interface DfdInfo {
  state: DfdState
  latest_id: string | null
  written_against: string | null
  error: string | null
}

export interface RiskDetail {
  risk: Risk
  elements: Record<string, ElementDetail | null>
  dfd: DfdInfo
  editors_since_approval: string[]
  duplicate: Risk | null
}

export interface Change {
  seq: number
  at: string
  op: string
  tbl: string
  row_key: string
  actor: string
  diff: Record<string, [unknown, unknown]>
  note: string
  prev_hash: string
  hash: string
}

export interface Approval {
  id: string
  version: string | null
  sha256: string | null
  ids: string[] | string | null
  approved_by: string | null
  approved_at: string | null
  note: string | null
}

export interface RiskWriteResponse {
  risk: Risk
}

export interface ApprovalWriteResponse {
  approval: Approval
}

export interface Conflict409 {
  detail: string
  current?: Risk
  current_sha256?: string | null
}

export interface DfdResponse {
  status: { state: DfdState; latest: Approval | null; current_sha256: string | null }
  approvals: Approval[]
  preview: {
    version: string | null
    sha256: string
    ids: string[]
    details: Record<string, ElementDetail>
    added: string[]
    removed: string[]
    warnings: string[]
  } | null
  preview_error: string | null
  text: string | null
}
