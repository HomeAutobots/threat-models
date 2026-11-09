"""Shared fixtures: a temp project with a git-tracked framework, registries, sessions, candidates."""
import contextlib
import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tmreg import db, ledger
from tmreg.core import Registry, ReviewerSession

# Copied from tests/test_dfd.py (the final, strict-parser fixture). The mermaid fence holds a
# table-like row that the parser must ignore.
SAMPLE_DFD = b"""| Field | Value |
|---|---|
| DFD version | 1.0 |

```mermaid
flowchart LR
  | E99 | not a table |
```

| ID | Element | Type |
|---|---|---|
| E1 | Customer | External entity |
| P1 | Web | Process |
| P2 | Gateway | Process |
| D1 | DB | Data store |

| ID | From | To | Label |
|---|---|---|---|
| F1 | E1 | P1 | HTTPS |
| F2 | P1 | P2 (via CDN) | REST |
| F3 | P2 | D1 | SQL |

| ID | Boundary | What enforces it |
|---|---|---|
| TB1 | Internet to edge | WAF |

| Class | Examples |
|---|---|
| PII | name |
"""

# A mini docs/reference/reference-system.md. The catalog section holds T-01, T-02, and PT-01;
# the tables before and after it are outside the section and must not be read as catalog rows.
SAMPLE_CATALOG = """---
kind: reference
title: Reference system
---
# Reference system

## Elements

| ID | Element | Type |
|---|---|---|
| E1 | Customer | External entity |

## Threat catalog used in worked examples

One canonical description and one STRIDE letter per threat.

| ID | Element(s) | Category | Threat |
|---|---|---|---|
| T-01 | E1, F1 | S | Credential stuffing with breached password lists against the customer login on F1; self-registration means no identity proofing |
| T-02 | F2, P2 | T | An attacker posts a forged or replayed payment-result body to P2's public webhook ingress and an unpaid order is marked paid |

Privacy threats keep their own sequence.

| ID | Element(s) | Category | Privacy threat |
|---|---|---|---|
| PT-01 | D1 | Linking | Order history in D1 shares a customer ID with receipts and has no retention limit, so any read access reconstructs one person's purchases over years |

## Using the catalog on a new page

| ID | Element(s) | Category | Threat |
|---|---|---|---|
| T-99 | X9 | S | Outside the catalog section; a parser must stop at the next heading |
"""

# A mini docs/templates/threat-model-document.md: front matter and prose around one
# ````markdown block, which is the part init_system turns into threat-model.md.
SAMPLE_TEMPLATE = """---
kind: template
title: Threat model document
---
# Threat model document

## How to use

Copy the block below into `docs/threat-model.md` and replace every `<angle bracket>` prompt.

````markdown
# Threat model: <system or feature name>

| Field | Value |
|---|---|
| System / feature | <name, plus one line on what it does> |
| Model version | <1.0, 1.1, ...> |

## 1. Scope and objectives

*What decision this model has to support, and what is inside the boundary.*

## 2. System model

*The diagram plus the tables that name everything the threats will later refer to.*

```mermaid
flowchart LR
  %% paste or embed the level-1 DFD
```

| ID | Element | Type | Notes |
|---|---|---|---|
| <P1> | <name> | <External entity / Process / Data store> | <what it does> |

## 3. Assumptions

*Everything the model treats as true without analyzing it.*

## 4. Threats and treatments

*What you found and what you are doing about it.*

| Threat | Element(s) | Category | Score | Treatment | Owner | Status | Register |
|---|---|---|---|---|---|---|---|
| <T-01> | <IDs> | <STRIDE / LINDDUN letter> | <score> | <treatment> | <name> | <status> | <link> |

## 5. Residual risk and acceptances

*What remains after the treatments land.*
````

## Notes on filling it in

- Keep it in the repository.
"""

# SAMPLE_DFD's IDs by kind, as dfd_approve would record them. seed_dfd_era writes them.
SAMPLE_DFD_IDS = {"E": ["E1"], "P": ["P1", "P2"], "D": ["D1"], "F": ["F1", "F2", "F3"], "TB": ["TB1"]}

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_WORKSPACE = (FIXTURES / "c4" / "sample.dsl").read_bytes()

_PROJECT_TOML = """framework_path = "framework"
reviewer_name = "Test Reviewer"
reviewer_email = "reviewer@example.com"
"""

_GIT_COMMIT = ["-c", "user.name=test", "-c", "user.email=test@example.com",
               "-c", "commit.gpgsign=false", "commit", "-q", "--no-verify", "--allow-empty",
               "-m", "framework fixture"]

_OPEN: list[Registry] = []


def make_project(tmp: Path) -> Path:
    """Write project.toml and a framework dir (catalog + template) committed to its own git repo."""
    root = Path(tmp)
    fw = root / "framework"
    for rel, text in (("docs/reference/reference-system.md", SAMPLE_CATALOG),
                      ("docs/templates/threat-model-document.md", SAMPLE_TEMPLATE)):
        (fw / rel).parent.mkdir(parents=True, exist_ok=True)
        (fw / rel).write_text(text)
    (root / "project.toml").write_text(_PROJECT_TOML)
    for args in (["init", "-q"], ["add", "-A"], _GIT_COMMIT):
        subprocess.run(["git", "-C", str(fw), *args], check=True, capture_output=True)
    return root


def make_registry(tmp, *, slug="demo", approve=True, trial=False, legacy=False,
                  root: Path | None = None) -> Registry:
    """A registry with one system and SAMPLE_WORKSPACE; approved as MODEL-1 unless approve=False.

    With root, reuse that project (for example, a trial database beside a real one).
    """
    root = make_project(tmp) if root is None else Path(root)
    if legacy:
        sysdir = root / "systems" / slug
        sysdir.mkdir(parents=True, exist_ok=True)
        (sysdir / "system.toml").write_text(
            'name = "Demo"\nlegacy_catalog = "docs/reference/reference-system.md"\n')
    reg = Registry(root, trial=trial)
    _OPEN.append(reg)
    reg.init_system(slug, "Demo")
    write_model(reg, slug)
    if approve:
        approve_model(reg, slug)
    return reg


def write_model(reg: Registry, slug: str, data: bytes = SAMPLE_WORKSPACE) -> None:
    (reg.root / "systems" / slug / "workspace.dsl").write_bytes(data)


def approve_model(reg: Registry, slug: str, note: str = "Checked against the DFD checklist.") -> dict:
    """Approve the current workspace.dsl, bound to its own sha256."""
    data = (reg.root / "systems" / slug / "workspace.dsl").read_bytes()
    return reg.c4_approve(session(), slug, note, expected_sha256=hashlib.sha256(data).hexdigest())


def write_dfd(reg: Registry, slug: str, data: bytes = SAMPLE_DFD) -> None:
    """For the DFD commands and endpoints, which stay until the DFD code is removed."""
    (reg.root / "systems" / slug / "dfd.md").write_bytes(data)


def seed_dfd_era(reg: Registry, slug: str = "demo") -> dict:
    """Record DFD-1 (SAMPLE_DFD's IDs) the way dfd_approve did, without dfd.md: a register from
    before the C4 model, for adoption and DFD-era tests. Bumps the DFD sequence, so verify stays clean."""
    with reg.conn:
        ledger.write_row(reg.conn, slug, "dfd_approvals", "DFD-1", {
            "version": "1.0", "sha256": hashlib.sha256(SAMPLE_DFD).hexdigest(),
            "ids": {k: list(v) for k, v in SAMPLE_DFD_IDS.items()},
            "approved_by": "Test Reviewer", "approved_at": db.now(),
            "note": "Checked against the DFD checklist.",
        }, op="dfd-approve", actor="human:Test Reviewer")
        reg.conn.execute(f"UPDATE {db.table(slug, 'sequences')} SET next = MAX(next, 2) "
                         "WHERE prefix = 'DFD'")
    return reg.dfd_approvals(slug)[0]


def seed_dfd_risk(reg: Registry, risk_id: str, elements: list[str], *, slug: str = "demo",
                  **fields) -> dict:
    """A risk drafted against DFD-1, written through the ledger as add_risk once wrote it (add now
    needs a model approval). fields override the row, e.g. review_state="approved". Bumps the
    risk's sequence, so verify stays clean."""
    at = db.now()
    actor = fields.get("drafted_by", "ai:20261101-01")
    row = {**ai_fields(elements=elements), "status": "open", "review_state": "pending",
           "drafted_by": actor, "dfd_approval_id": "DFD-1", "detail_complete": 1,
           "created_at": at, "updated_at": at, **fields}
    prefix, n = risk_id.rsplit("-", 1)
    with reg.conn:
        ledger.write_row(reg.conn, slug, "risks", risk_id, row, op="add", actor=actor)
        reg.conn.execute(f"UPDATE {db.table(slug, 'sequences')} SET next = MAX(next, ?) "
                         "WHERE prefix = ?", (int(n) + 1, prefix))
    return reg.get_risk(slug, risk_id)


@contextlib.contextmanager
def human_terminal(tty: bool = True):
    """Patch the terminal check and drop CLAUDECODE, which is set when the suite itself runs under
    Claude Code. os.environ is restored on exit."""
    with mock.patch("tmreg.core._has_tty", return_value=tty), mock.patch.dict(os.environ):
        os.environ.pop("CLAUDECODE", None)
        yield


def session() -> ReviewerSession:
    with human_terminal():
        return ReviewerSession("Test Reviewer", "reviewer@example.com")


def ai_fields(**overrides) -> dict:
    """A valid AI-drafted candidate against SAMPLE_WORKSPACE (catalog-style T-17: C2 trusts
    forwarded headers)."""
    base = {
        "title": "C2 trusts client-supplied forwarded headers",
        "elements": ["C2", "R2"],
        "category": "T",
        "method": "stride-per-element",
        "origin": "threat-model",
        "origin_ref": "tm-model run",
        "description": ("C2 trusts the X-Forwarded-For and X-Forwarded-Host headers that arrive on R2, "
                        "so a caller can change routing or its apparent source address."),
        "attack_scenario": ("An unauthenticated internet caller sends requests through C1 with forged "
                            "forwarded headers; C2 uses them for routing and rate-limit keys, so the "
                            "caller reaches internal routes and evades per-source limits. Path: direct."),
        "impact": "Requests reach internal-only routes; per-source rate limits and audit attribution fail.",
        "likelihood": "medium",
        "likelihood_rationale": "Header spoofing needs no credentials, and C1 forwards headers unchanged.",
        "implemented_controls": "none identified",
        "recommended_controls": "Strip and re-set forwarded headers at C1; C2 trusts them only from C1.",
        "assumptions": "C1 does not already normalize forwarded headers.",
        "evidence": "workspace.dsl v1.0 (C2, R2); guide catalog T-17.",
        "ai_confidence": "medium",
    }
    return {**base, **overrides}


def start(reg: Registry, slug: str = "demo") -> str:
    return reg.start_run(slug)["run_id"]


def close_registries() -> None:
    while _OPEN:
        _OPEN.pop().close()


class TmpTestCase(unittest.TestCase):
    """setUp gives self.tmp (a Path); registries from make_registry are closed after each test."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.tmp = Path(d.name)
        self.addCleanup(close_registries)
