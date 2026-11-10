import real from './fixtures/c4-real.json'
import type { C4Item, C4Rel, C4Response, CitedItem, CitedState, ModelEntry, ModelInfo, Risk } from './api/types'

export function item(over: Partial<C4Item> & { name: string }): C4Item {
  return {
    kind: 'container', description: null, technology: null, tags: [], properties: {}, parent: null,
    group: null, role: null, where: [], zones: {}, ...over,
  }
}

export function rel(over: Partial<C4Rel> & { source: string; destination: string }): C4Rel {
  return {
    description: null, technology: null, tags: [], properties: {}, role: 'Data flow', crossings: {}, ...over,
  }
}

export const RECORD = {
  items: {
    A1: item({ kind: 'person', name: 'Customer', role: 'External entity', where: ['A1'] }),
    S1: item({ kind: 'softwareSystem', name: 'Shop', where: ['S1'] }),
    C1: item({ name: 'Web app', role: 'Process', technology: 'React', parent: 'S1', where: ['S1', 'C1'], zones: { ENV1: ['TB1'] }, properties: { 'tm.owner': 'Team Web', 'tm.zoom': 'holds the checkout' } }),
    C2: item({ name: 'Orders API', role: 'Process', technology: 'Python', parent: 'S1', where: ['S1', 'C2'], zones: { ENV1: ['TB2'] } }),
    K1: item({ kind: 'component', name: 'Cart', role: 'Process', parent: 'C2', where: ['S1', 'C2', 'K1'] }),
    ENV1: item({ kind: 'deploymentEnvironment', name: 'Production', where: ['ENV1'] }),
    TB1: item({ kind: 'deploymentNode', name: 'Internet edge', parent: 'ENV1', properties: { 'tm.enforced_by': 'the load balancer' }, where: ['ENV1', 'TB1'] }),
    TB2: item({ kind: 'deploymentNode', name: 'Cloud', parent: 'ENV1', where: ['ENV1', 'TB2'] }),
    N1: item({ kind: 'deploymentNode', name: 'Prod host', technology: 'Linux', parent: 'TB1', where: ['ENV1', 'TB1', 'N1'] }),
  },
  rels: {
    R1: rel({ source: 'C1', destination: 'C2', description: 'Places orders', technology: 'HTTPS', properties: { 'tm.data.sent': 'order', 'tm.data.returned': 'receipt', 'tm.auth': 'OAuth token' }, crossings: { ENV1: ['TB1', 'TB2'] } }),
  },
  views: {
    SEQ1: { kind: 'dynamic', scope: 'S1', env: null, title: 'Checkout', steps: ['R1'] },
  },
}

export type RealKey = 'changed' | 'nofile' | 'first' | 'adoption'

/** A real GET /c4 body, generated through the back end's TestClient (see fixtures/c4-real.json). */
export const realC4 = (key: RealKey): C4Response => structuredClone(real[key]) as unknown as C4Response

const APPROVAL = { id: 'MODEL-1', version: '1.0', sha256: 'a', ids: {}, approved_by: 'human:ann', approved_at: '2026-01-02T03:04:00Z', note: 'first one' }

export function c4(over: Partial<C4Response> = {}): C4Response {
  return {
    status: { state: 'changed', latest: APPROVAL, current_sha256: 'cur' },
    approvals: [APPROVAL],
    preview: {
      sha256: 'sha-seen', version: '1.1', ids: {}, record: RECORD, added: ['C3'], removed: ['C9'],
      changed: { C2: ['description', 'technology'] }, warnings: [], next_ids: {}, reused: [], problems: [],
      diff: ['-old line', '+new line'], adoption: null,
    },
    error: null,
    text: 'workspace {}',
    counts: { C2: { open: 1, pending: 1 } },
    latest_record: RECORD,
    structurizr: { state: 'not-checked', message: null, base: null, views: [] },
    ...over,
  }
}

export function risk(id: string, elements: string[], over: Partial<Risk> = {}): Risk {
  return { id, title: `Title ${id}`, elements, review_state: 'approved', status: 'open', merged_into: null, ...over } as Risk
}

/** The `model` key of a risk detail. */
export function modelInfo(over: Partial<ModelInfo> = {}): ModelInfo {
  return { state: 'current', latest_id: 'MODEL-1', written_against: 'MODEL-1', moved_on: false, changed: [], basis: 'model', ...over }
}

/** One entry of a risk detail's `elements`. */
export function cited(state: CitedState, written: ModelEntry | null, latest: ModelEntry | null = null): CitedItem {
  return { written, latest, state }
}
