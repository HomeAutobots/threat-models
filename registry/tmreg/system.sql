CREATE TABLE {p}__risks (
    id TEXT PRIMARY KEY,
    title TEXT,
    elements TEXT,
    category TEXT,
    method TEXT,
    origin TEXT,
    origin_ref TEXT,
    description TEXT,
    attack_scenario TEXT,
    attack_path TEXT,
    impact TEXT,
    impact_rating TEXT,
    likelihood TEXT,
    likelihood_rationale TEXT,
    score TEXT,
    score_method TEXT,
    assumptions TEXT,
    implemented_controls TEXT,
    recommended_controls TEXT,
    control_refs TEXT,
    exception_ref TEXT,
    treatment TEXT,
    decision_requested TEXT,
    evidence TEXT,
    ai_confidence TEXT,
    owner TEXT,
    due TEXT,
    status TEXT,
    status_reason TEXT,
    test TEXT,
    ticket TEXT,
    notes TEXT,
    review_state TEXT,
    last_approved TEXT,
    drafted_by TEXT,
    reviewed_by TEXT,
    reviewed_at TEXT,
    review_note TEXT,
    possible_duplicate_of TEXT,
    merged_into TEXT,
    dfd_approval_id TEXT,
    model_approval_id TEXT,
    detail_complete INTEGER,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE {p}__changes (
    seq       INTEGER PRIMARY KEY AUTOINCREMENT,
    at        TEXT NOT NULL,
    op        TEXT NOT NULL,
    tbl       TEXT NOT NULL,
    row_key   TEXT NOT NULL,
    actor     TEXT NOT NULL,
    diff      TEXT NOT NULL,
    note      TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash      TEXT NOT NULL
);

CREATE TABLE {p}__dfd_approvals (
    id          TEXT PRIMARY KEY,
    version     TEXT,
    sha256      TEXT,
    ids         TEXT,
    approved_by TEXT,
    approved_at TEXT,
    note        TEXT
);

CREATE TABLE {p}__model_approvals (
    id          TEXT PRIMARY KEY,
    version     TEXT,
    sha256      TEXT,
    ids         TEXT,
    model       TEXT,
    source      TEXT,
    approved_by TEXT,
    approved_at TEXT,
    note        TEXT
);

CREATE TABLE {p}__runs (
    run_id           TEXT PRIMARY KEY,
    started_at       TEXT,
    framework_commit TEXT,
    dfd_approval_id  TEXT,
    model_approval_id TEXT,
    methods          TEXT,
    actor            TEXT
);

CREATE TABLE {p}__sequences (
    prefix TEXT PRIMARY KEY,
    next   INTEGER NOT NULL
);

CREATE TRIGGER {p}__risks_no_delete BEFORE DELETE ON {p}__risks
BEGIN SELECT RAISE(ABORT, 'risk rows cannot be deleted'); END;

CREATE TRIGGER {p}__changes_no_update BEFORE UPDATE ON {p}__changes
BEGIN SELECT RAISE(ABORT, 'change log is append-only'); END;

CREATE TRIGGER {p}__changes_no_delete BEFORE DELETE ON {p}__changes
BEGIN SELECT RAISE(ABORT, 'change log is append-only'); END;

CREATE TRIGGER {p}__dfd_approvals_no_update BEFORE UPDATE ON {p}__dfd_approvals
BEGIN SELECT RAISE(ABORT, 'DFD approvals are append-only'); END;

CREATE TRIGGER {p}__dfd_approvals_no_delete BEFORE DELETE ON {p}__dfd_approvals
BEGIN SELECT RAISE(ABORT, 'DFD approvals are append-only'); END;

CREATE TRIGGER {p}__model_approvals_no_update BEFORE UPDATE ON {p}__model_approvals
BEGIN SELECT RAISE(ABORT, 'model approvals are append-only'); END;

CREATE TRIGGER {p}__model_approvals_no_delete BEFORE DELETE ON {p}__model_approvals
BEGIN SELECT RAISE(ABORT, 'model approvals are append-only'); END;
