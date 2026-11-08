"""Shared fixtures: a temp project with a git-tracked framework, registries, sessions, candidates."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
    """A registry with one system and SAMPLE_DFD; approved as DFD-1 unless approve=False.

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
    (root / "systems" / slug / "dfd.md").write_bytes(SAMPLE_DFD)
    if approve:
        reg.dfd_approve(session(), slug, "Checked against the DFD checklist.")
    return reg


def session() -> ReviewerSession:
    with mock.patch("tmreg.core._has_tty", return_value=True):
        return ReviewerSession("Test Reviewer", "reviewer@example.com")


def ai_fields(**overrides) -> dict:
    """A valid AI-drafted candidate against SAMPLE_DFD (catalog-style T-17: P2 trusts forwarded headers)."""
    base = {
        "title": "P2 trusts client-supplied forwarded headers",
        "elements": ["P2", "F2"],
        "category": "T",
        "method": "stride-per-element",
        "origin": "threat-model",
        "origin_ref": "tm-model run",
        "description": ("P2 trusts the X-Forwarded-For and X-Forwarded-Host headers that arrive on F2, "
                        "so a caller can change routing or its apparent source address."),
        "attack_scenario": ("An unauthenticated internet caller sends requests through P1 with forged "
                            "forwarded headers; P2 uses them for routing and rate-limit keys, so the "
                            "caller reaches internal routes and evades per-source limits. Path: direct."),
        "impact": "Requests reach internal-only routes; per-source rate limits and audit attribution fail.",
        "likelihood": "medium",
        "likelihood_rationale": "Header spoofing needs no credentials, and P1 forwards headers unchanged.",
        "implemented_controls": "none identified",
        "recommended_controls": "Strip and re-set forwarded headers at P1; P2 trusts them only from P1.",
        "assumptions": "P1 does not already normalize forwarded headers.",
        "evidence": "dfd.md v1.0 (F2, P2); guide catalog T-17.",
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
