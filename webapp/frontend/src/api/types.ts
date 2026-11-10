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
  evidence: string | null
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

/** An item, a path or a dynamic view of a model record, as the risk detail returns it. */
export type ModelEntry = C4Item | C4Rel | C4View

export type CitedState = 'same' | 'changed' | 'removed' | 'dfd'

export interface CitedItem {
  written: ModelEntry | null
  latest: ModelEntry | null
  state: CitedState
}

export interface ModelInfo {
  state: ModelState
  latest_id: string | null
  written_against: string | null
  moved_on: boolean
  changed: string[]
  basis: 'model' | 'dfd'
}

export interface RiskDetail {
  risk: Risk
  elements: Record<string, CitedItem>
  model: ModelInfo
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

// ---- C4 model (api_read.py c4, c4/routes; api_write.py c4/approve, c4/export) --------------------

export type ModelState = 'none' | 'current' | 'changed'

export interface C4Item {
  kind: string
  name: string
  description: string | null
  technology: string | null
  tags: string[]
  properties: Record<string, string>
  parent: string | null
  group: string | null
  role: string | null
  where: string[]
  zones: Record<string, string[]>
}

export interface C4Rel {
  source: string
  destination: string
  description: string | null
  technology: string | null
  tags: string[]
  properties: Record<string, string>
  role: string | null
  crossings: Record<string, string[]>
}

export interface C4View {
  kind: string
  scope: string | null
  env: string | null
  title: string | null
  steps: string[]
}

export interface C4Record {
  version?: string | null
  name?: string | null
  description?: string | null
  items: Record<string, C4Item>
  rels: Record<string, C4Rel>
  views: Record<string, C4View>
}

export interface ModelApproval {
  id: string
  version: string | null
  sha256: string | null
  ids: Record<string, string[]> | null
  approved_by: string | null
  approved_at: string | null
  note: string | null
}

export interface Adoption {
  gaps: { id: string; cited_by: string[] }[]
  pending_rereviews: string[]
  rewrites?: Record<string, unknown>
}

export interface C4Preview {
  sha256: string
  version: string | null
  ids: Record<string, string[]>
  record: C4Record
  added: string[]
  removed: string[]
  changed: Record<string, string[]>
  warnings: string[]
  next_ids: Record<string, string>
  reused: string[]
  problems: string[]
  diff: string[]
  adoption: Adoption | null
}

export interface ExportView {
  key: string
  url: string
}

export interface StructurizrVerdict {
  state: 'accepted' | 'refused' | 'not-checked'
  message: string | null
  base: string | null
  views: ExportView[]
}

export interface C4Response {
  status: { state: ModelState; latest: ModelApproval | null; current_sha256: string | null }
  approvals: ModelApproval[]
  preview: C4Preview | null
  error: string | null
  text: string
  counts: Record<string, { open: number; pending: number }>
  latest_record: C4Record | null
  structurizr: StructurizrVerdict
}

export interface C4ExportResponse extends StructurizrVerdict {
  sha256: string
}

export interface RouteRisks {
  open: string[]
  pending: string[]
}

export interface RouteHop {
  path: string
  from: string
  to: string
  against_arrow: boolean
  crossings: Record<string, string[]>
  risks: RouteRisks
}

export interface RouteChain {
  hops: RouteHop[]
  elements: Record<string, RouteRisks>
}

export interface C4RoutesResponse {
  chains: RouteChain[]
}
