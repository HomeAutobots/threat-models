# Web app: design

Status: draft for the owner's approval, 2026-11-08. Builds on `webapp/DESIGN.md` (the design
template and the three static mockups) and settles what it left open: the stack, sign-in, the
terminal check, and the edit rule.

## 1. Intent

The owner has never used the terminal for threat models, because a threat is too hard to read
there. The web app becomes the owner's main way to work with the registry: read a risk in full,
decide on it, and edit, manage, and approve risks. It replaces the terminal for everyday work. It
does not replace the registry's rules: the web app is a second front end on the same core code as
`./tmreg`.

The owner decides on the full record, never a skim. The review page exists to give a complete
and accurate understanding of one threat before a decision.

## 2. Goals, non-goals, anti-goals

Goals (MVP):
- Review pending risks one at a time, on a page that shows the full record (section 6.1).
- Browse the register, open any risk, edit it, change its status, and retire it.
- Add a risk by hand.
- Approve a system's DFD, see the change log and the `verify` result, and download reports.
- Work on the real register and on the trial register, never mixing them up.

Non-goals (MVP):
- More than one user, accounts, or SSO. One reviewer, the one named in `project.toml`.
- Proving the human per approval (Touch ID, signed approvals). That is the upgrade path, later.
- Creating a system, the one-time legacy import, and editing `dfd.md` in the browser. These stay
  in the terminal for now.
- Running modeling (`/tm-model`) from the web app.

Anti-goals (a failure even if everything works):
- An AI agent can change anything through the web app, or can reach its API at all.
- An AI change to an approved risk takes effect without the owner seeing it in review.
- Any way to approve, reject, or retire more than one risk per action.
- The web app and the CLI disagree on a rule, because the web app checks something itself.
- The review page hides, truncates, or summarizes away any field.
- The app sends anything off the machine: no CDN, no web fonts, no telemetry.
- Risk data ends up in git.

## 3. Decisions

| Decision | Choice | Who |
|---|---|---|
| Users | Just the owner for now; maybe others later | Owner |
| Scope | MVP; improve how approvals prove the human later | Owner |
| Agent access | Signed-in use only; no API keys; the agent has no way to make changes through the web app | Owner |
| API | A JSON API between front end and back end, so capabilities are not limited, locked to the signed-in browser | Owner |
| Frameworks | Battle-tested frameworks, kept simple; no hand-rolled server or UI | Owner |
| Stack | FastAPI back end; React with TypeScript, built with Vite; Mantine components | My call |
| Review page | Full record, every field, in nine numbered sections, with a decision panel beside it (section 6.1) | Owner approved the mockup |
| Managing an approved risk | Edit it, change its status, retire it | Owner |
| The edit rule | Edits by the signed-in owner (or the owner's own terminal) apply directly and keep the approval. Edits by AI send the risk back to review, and the owner is notified | Owner |
| Sign-in | A one-time link printed in the Terminal window that started the app | My call |
| After a human adds a risk | It lands pending (unchanged rule), and the app opens its review page right away | My call |
| The guide | Updated in the same work to match the new edit rule and the built web app (section 9) | Owner |
| Element details on the review page | Read from the current `dfd.md`, labeled with their source, and flagged when the DFD has changed since the risk was written (section 6.1) | My call |
| Imported one-liners the owner fills in | The owner's edit sets `detail_complete` when every AI-required field is filled, the same check `approve` uses (section 5.4) | My call |
| Reason on a status change | Stored as the edit's change-log note; `status_reason` stays set only by `retire` (section 6.4) | My call |
| DFD screen | A readable view (no raw HTML, mermaid drawn in strict mode) and an exact-file view, with a banner when the readable view hides something (section 6.5) | My call |

## 4. Constraints

- tmreg stays Python 3.11+, standard library only. The web app's dependencies live only under
  `webapp/`, and nothing in `registry/` imports them.
- The guard stays Python 3.9+, standard library only. `make test` keeps working with no web
  dependencies installed.
- Every rule lives in `registry/tmreg/core.py`. The server parses a request, calls one `Registry`
  method, and returns the result or the `RegistryError` message. It validates nothing itself.
  The front end gets vocabularies, labels, and minimum lengths from the server (from `model.py`)
  instead of hard-coding them.
- The rules of `webapp/DESIGN.md` section 1 hold: no select-all, no multi-item endpoint, no
  approval without a note, approve only what was shown, every create lands pending.
- Risk data never enters git (`.githooks/`). Mockups, fixtures, and tests use sample data from the
  guide's reference system only.
- The server listens on `127.0.0.1` only.
- Dependencies are pinned to exact versions with lockfiles (`uv.lock`, `package-lock.json`).

## 5. Architecture

### 5.1 Pieces

- `webapp/backend/`: a FastAPI app that imports `tmreg` from `registry/` and serves both the JSON
  API (under `/api/`) and the built front end. Managed with uv (`pyproject.toml`, `uv.lock`).
- `webapp/frontend/`: React + TypeScript + Vite + Mantine, with React Router for pages and
  TanStack Query for API calls. `npm run build` writes `dist/`, which the back end serves. No
  asset is loaded from the network at run time.
- `webapp/mockups/` and `webapp/DESIGN.md` stay as references. `DESIGN.md` is updated in the same
  change to describe what is built.
- One `Registry` instance per request, closed after it (SQLite connections are per thread).

### 5.2 Starting the app and signing in

- The owner starts the app with `make web`, or by double-clicking a `.command` file in `webapp/`,
  which opens Terminal and runs the same thing. The first start installs the pinned dependencies
  and builds the front end. Later starts skip what is already current.
- Before anything else, the server calls `core.require_interactive("web")`. It refuses to start
  without an interactive terminal or when `CLAUDECODE` is set, exactly like the human-only
  commands. A Claude Code shell cannot start it.
- The server prints a one-time sign-in link, `http://127.0.0.1:<port>/signin?token=<random>`,
  in that Terminal window and nowhere else. The token is 32 random bytes from `secrets`, held only
  in memory, and works once. Opening it sets the session cookie and redirects to `/#k=<token>`,
  where the token is the session's CSRF token (section 5.3). The front end keeps that token in
  `localStorage` and removes `#k=` from the address bar. The server writes nothing about sign-in
  to disk: the sign-in token, the session, and the CSRF token live in its memory only. The browser
  does keep some of it: the CSRF token in `localStorage`, and the used sign-in link and the `/#k=`
  URL may appear in its history. None of it works once the server stops.
- The session lasts until the server stops. Closing the Terminal window stops the server and signs
  the owner out. Restarting prints a new link.
- Human-only operations still build a `ReviewerSession` from `project.toml`. Core's existing
  terminal check passes because the server runs in the owner's Terminal window. If the server
  ever runs detached (no terminal), the check fails and those operations refuse: it fails closed.
  The sign-in cookie decides which requests reach those operations at all.

### 5.3 The API lock

Every `/api/` route, read or write, requires a valid session. On top of that:
- **Cookie.** A random session ID, `HttpOnly`, `SameSite=Strict`, `Path=/`. Page scripts cannot
  read it. Cookies are shared across `localhost` ports, so any other local server the owner opens
  in the browser would receive it. The cookie alone therefore opens nothing.
- **CSRF token.** The sign-in redirect goes to `/#k=<token>`. The fragment never reaches a server
  or a `Referer`. The front end keeps the token in `localStorage`, which is per origin, so per
  port. Every `/api` request, reads included, must send it in the `X-CSRF-Token` header along
  with the cookie. Without both, the answer is 401. Every write must also carry an `Origin` equal
  to the app's own origin.
- **Host check.** Requests whose `Host` is not `127.0.0.1:<port>` or `localhost:<port>` are
  refused, which blocks DNS rebinding from a web page.
- **Content-Security-Policy and `no-store`.** Every response carries a Content-Security-Policy that
  allows the app's own origin only, plus `data:` and `blob:` images, `data:` fonts, and inline
  styles; scripts and connections are own-origin only. Every `/api` response carries
  `Cache-Control: no-store`. Only http and lifespan connections are served; websockets are refused.
- **No other way in.** No API keys, bearer tokens, or stored passwords. No CORS.
- **One item per write.** Every write route names one system and at most one risk ID in its path.

What this stops: any script or agent without the browser's cookie and CSRF token, including a Claude session
outside the guard that can make web requests. A guarded modeling session cannot make web requests
at all.

What it does not stop, and the README must say so: a browser-automation tool working inside the
owner's signed-in browser, such as Claude in Chrome. For the MVP, never grant such an extension
access to `127.0.0.1` or `localhost`. The per-approval proof (Touch ID or signed approvals,
`webapp/DESIGN.md` section 5) closes this later.

As defense in depth, `threat-models/.claude/settings.json` gains a deny rule for
`Edit(/webapp/**)`. The guard's allow-list already blocks starting the server and every web
request command. The settings also deny the browser and desktop automation MCP servers
(`mcp__claude-in-chrome`, `mcp__Claude_Browser`, `mcp__computer-use`, and `mcp__remote-devices`,
which hosts the remote browser and computer tools), and `/tm-model` disallows them, so a guarded
session cannot drive the signed-in browser. A session started elsewhere can, which is why the
rule above still holds.

### 5.4 Core changes in tmreg

These are deliberate rule changes, owner-decided, each with unit tests in `registry/tests/` and
an adversarial review before commit:

1. **The edit rule.** In `Registry.edit_risk`, an edit to an approved risk by a human actor
   (`human:<name>`, which `_actor` grants only at an interactive terminal outside Claude Code)
   applies directly, and the risk stays approved. Its `reviewed_by`, `reviewed_at`, and
   `review_note` keep describing the last review. The change log records the edit, the human
   actor, and the optional reason. An edit by an AI actor (`ai:<run-id>`) works as today: the
   risk goes back to pending with `last_approved` set. A human edit of a pending risk leaves it
   pending. Because an AI edit always moves an approved risk to pending first, a human edit can
   never quietly approve AI content. A human edit that keeps an approval also applies the check
   `approve` uses for imported one-liners: if `detail_complete` is 0 and every `AI_REQUIRED` field
   is now filled, it sets `detail_complete` to 1. That way an imported catalog row the owner fills
   in stops being reported as "detail incomplete".
2. **Edit takes `seen` and a reason.** `edit_risk` gains keyword-only `seen` (as on `approve`,
   raising `StaleRecord` if the row changed since it was shown) and an optional `note`, stored as
   the change log's note. The web app always passes `seen`. The CLI keeps working without either.
3. **DFD element details.** `dfd.py` additionally returns each ID's details from the `dfd.md`
   tables: name, type, and description for elements; from, to, and label for flows; name and
   enforcement for trust boundaries. Read-only, for display. Parsing rules and the hash do not
   change.

No change to `ReviewerSession`, `require_interactive`, or the human-only commands.

## 6. Screens

All screens are scoped to one system and one register, chosen in the header. Text is never
truncated on a risk's page. Dates show as absolute local times. AI and human authorship are
always labeled. Accessibility target: WCAG 2.1 AA (keyboard use, visible focus, color never the
only signal, light and dark mode).

### 6.1 Review page (approved by the owner)

The approved mockup is
`threat-models-dev/.superpowers/brainstorm/50416-1794188720/content/review-full-record.html`
(local to the dev workspace). Copy it to `webapp/mockups/review-full-record.html` in the
same change.

- Header: queue position ("1 of 2 pending"), Previous and Next (navigation only), the risk ID and
  title, and badges for review state, new draft or re-review, drafted by (AI run or human), and AI
  confidence.
- Banners: possible duplicate (links to section 8 of the page), and "DFD has moved on" when
  `dfd_status` is `changed` (links to the DFD screen and does not block review).
- For a re-review, a "What changed" table comes first: field, last approved value, proposed
  value. Unchanged fields are collapsed.
- The full record in nine numbered sections, every field shown, empty ones as "Not provided":
  1. At a glance (category with its STRIDE or LINDDUN name, impact rating, likelihood, score,
     treatment, status), labeled as orientation only.
  2. Where it happens: each element and flow with its name, type, and DFD description, read from
     the current `dfd.md`. An approval stores only IDs and a hash, and real systems' `dfd.md` files
     have no history in git, so the text the risk was written against cannot be recovered. The
     section says which source it shows: "From DFD-<n> (current)" when the risk's
     `dfd_approval_id` is the latest approval and `dfd_status` is `current`. Otherwise it says
     "From the current dfd.md, which has changed since this risk was written against DFD-<n>",
     and it marks any cited ID missing from the current file as "Not in the current DFD".
  3. The threat: description, attack scenario, attack path.
  4. Impact and likelihood: impact, impact rating, likelihood, likelihood rationale, score,
     score method.
  5. Controls and assumptions: implemented controls, recommended controls, control references,
     assumptions.
  6. Treatment and ownership: treatment, decision requested, exception reference, owner, due,
     status, status reason.
  7. Evidence and tracking: evidence, origin and origin reference, method, test, ticket, notes.
  8. Possible duplicate: this draft and the other risk side by side (shown only when flagged).
  9. Record and history: review state, drafted by, last approved version, DFD approval, created
     and updated times, and the risk's change history.
- Decision panel, sticky beside the record (below it at narrow widths): a section list whose dots
  fill in as each section scrolls into view, the review note with a live count against the
  minimum, and Approve, Reject (labeled "Reject and restore last approved" on a re-review),
  Merge into the flagged duplicate (not on a re-review), and Edit before deciding. Approve and
  Reject stay disabled until the note meets the minimum.
- Stale record: the page keeps the record exactly as received and sends it back as `seen`. On
  `StaleRecord` the server writes nothing and returns the current record. The page shows it with
  the banner "This risk changed after you opened it. Review the current version." and keeps the
  typed note. Nothing retries on its own.
- After a decision, the page moves to the next pending risk or an empty-queue message.

### 6.2 Register

- Tabs: Approved, Pending review, Rejected, Retired, each with a count.
- Filters: status, element, category, origin, and a text search over ID and title.
- Columns: ID, title, elements, category, status, origin, drafted by, updated.
- Clicking a row opens the risk page. The Pending tab links to the review queue and offers no row
  actions.
- A banner when AI has changed approved risks: "2 approved risks were changed by AI and need your
  review", linking to the queue. These are pending risks with `last_approved` set.
- Buttons: Add risk, Report.

### 6.3 Risk page

The same full-record layout as section 6.1, with an action panel instead of the decision panel:
Edit, Change status, and Retire (approved risks only). A pending risk links to its review page.
Rejected and retired risks are read-only, as core requires.

### 6.4 Edit, status, retire, add

- **Edit** opens a form with every editable field (`EDITABLE_FIELDS`), grouped like the record,
  plus an optional "reason for change". Save sends the changed fields, `seen`, and the reason.
  The owner's edit to an approved risk stays approved. An edit to a pending risk stays pending.
- **Change status** is a short form: the status (open, planned, in progress, mitigated, accepted,
  won't fix) and an optional reason. It is an edit under the same rule, and the reason is stored
  as the edit's change-log note, shown in the risk's history. The record's `status_reason` field
  stays system-managed (only `retire` sets it), so `EDITABLE_FIELDS` and `SNAPSHOT_FIELDS` do not
  change.
- **Retire**: a reason of 20 characters or more, then a confirmation. Approved risks only.
- **Add risk**: the same form as Edit, empty, with the human-required fields marked. It lands
  pending, and the app opens its review page right away.
- Core's error messages show inline, next to the form.

### 6.5 DFD

The current status (none, current, changed), the list of approvals, `dfd.md`, and the preview of
added and removed IDs, with any risks that cite removed IDs. Approve DFD takes a note and sends
back the previewed `sha256` as the expected hash, so the owner approves exactly the file that was
previewed.

`dfd.md` is AI-writable, and the approval covers its exact bytes, so the screen has two views:
- **Readable** (the default): the markdown rendered with raw HTML disabled, and mermaid diagrams
  drawn by a bundled mermaid in its `strict` security mode.
- **Exact file**: the raw text, escaped, with non-printable characters shown as escapes, like the
  CLI's `visible()`.

If the file holds anything the readable view does not show or may display misleadingly, such as
HTML comments, raw HTML, or invisible or control characters (any character `visible()` escapes,
after CRLF line endings are normalized), a banner says so above Approve DFD and links to the Exact
file view.

### 6.6 History and verify

The system's change log: sequence number, time, actor (AI run or human), operation, row, and
note. The `verify` result sits at the top: "ok", or each problem it reports.

### 6.7 Reports

Format (md, csv, html) and the three include toggles (pending, rejected, retired). It shows a
preview and offers a download. Nothing is written into the repository.

### 6.8 Trial register

When `registry/trial.db` exists, the header offers Main and Trial. While Trial is selected, a
persistent, distinctly colored banner reads "Trial register: practice data, not the real
register". The choice is part of every API path, never a hidden setting.

## 7. API

All under `/api/`, all requiring the session. `{reg}` is `main` or `trial`. Every request needs the
session cookie and the CSRF header; writes also need the origin check.

| Method and path | Calls |
|---|---|
| `GET /api/session` | Reviewer name, whether a trial register exists |
| `GET /api/meta` | Field list, editable fields, labels, vocabularies, minimum lengths (from `model.py`) |
| `GET /api/{reg}/systems` | Systems in that register |
| `GET /api/{reg}/systems/{slug}/risks?state=` | `list_risks` |
| `GET /api/{reg}/systems/{slug}/risks/{id}` | `get_risk`, plus element details for its IDs |
| `GET /api/{reg}/systems/{slug}/risks/{id}/history` | `history` for one risk |
| `GET /api/{reg}/systems/{slug}/history` | `history` for the system |
| `GET /api/{reg}/systems/{slug}/verify` | `verify` |
| `GET /api/{reg}/systems/{slug}/dfd` | `dfd_status`, `dfd_preview`, element details, `dfd.md` text |
| `GET /api/{reg}/systems/{slug}/report?format=&include_…=` | `report` |
| `POST /api/{reg}/systems/{slug}/risks` | `add_risk` (human) |
| `POST /api/{reg}/systems/{slug}/risks/{id}/edit` | `edit_risk` with `seen` and the reason |
| `POST /api/{reg}/systems/{slug}/risks/{id}/approve` | `approve` with note and `seen` |
| `POST /api/{reg}/systems/{slug}/risks/{id}/reject` | `reject` with note and `seen` |
| `POST /api/{reg}/systems/{slug}/risks/{id}/merge` | `merge` into a named risk, with note and `seen` |
| `POST /api/{reg}/systems/{slug}/risks/{id}/retire` | `retire` with reason and `seen` |
| `POST /api/{reg}/systems/{slug}/dfd/approve` | `dfd_approve` with note and the expected `sha256` |

`RegistryError` returns 422 with core's message. `StaleRecord` returns 409 with the current
record. A missing or invalid session returns 401.

## 8. Tests

- `registry/tests/` (stdlib, part of `make test`): the new edit rule (human keeps the approval, AI
  sends it to review, human edit of pending stays pending), `seen` and the note on `edit_risk`,
  and the DFD element details.
- `webapp/backend` tests (pytest with FastAPI's test client), run by a new `make test-web`:
  - every route in the app refuses without a session (the test walks the app's route table, so a
    new route cannot be left open by accident);
  - a wrong `Host`, a missing CSRF header, and a foreign `Origin` are refused;
  - the sign-in token works once;
  - the server refuses to start without a terminal or with `CLAUDECODE` set;
  - `seen` reaches core unmodified, and `StaleRecord` returns 409 with nothing written;
  - every write path names exactly one system and at most one risk.
- `webapp/frontend` tests (Vitest and Testing Library): the decision panel stays disabled until
  the note meets the minimum, empty fields render as "Not provided", the stale banner keeps the
  typed note, and the trial banner shows in trial.
- `registry/tests/test_settings.py` requires the new `Edit(/webapp/**)` deny rule.

## 9. Documents to update in the same change

- `README.md`: a Web app section (start, sign-in, the trial switch), the edit rule, and under
  "What the guard blocks", the web app's lock and its Claude in Chrome limit.
- `threat-models/CLAUDE.md` (the agent's): AI edits still send a risk back to review; the web app
  is the owner's and off limits.
- `webapp/DESIGN.md`: rewritten to describe what is built, pointing here for the reasoning.
- `.gitignore`: `webapp/frontend/node_modules/`, `webapp/frontend/dist/`, `webapp/.venv/`.
- `threat-models-dev/CLAUDE.md`: the web app's dependencies are allowed under `webapp/` only,
  plus how to run the web tests.
- The guide (`~/Developer/threat-model-framework`), as part of this work (owner, 2026-11-08). Read
  its `CLAUDE.md` first and follow its rules. `make check` passes. Commits use `content:` or
  `chore:`. The changes go on its current branch, `feat/ai-assisted-threat-modeling`, which holds
  the spec. The places that state the old rule or the web app's old status:
  - `docs/superpowers/specs/2026-11-07-ai-assisted-threat-modeling-design.md`. Amend it in place,
    as the earlier amendment did, recording the new owner decisions dated 2026-11-08:
    - the scope list (item 4, "a web app design template") and the non-goal "Building the web
      app, a server, multi-user accounts, or authentication";
    - the decision rows "Interfaces now" and "Edits to an approved risk";
    - the operations table rows `edit` and `merge` (a merge's edit of the target is the human's,
      so the target keeps its approval);
    - section 8, "Web app design template (not built)", which now points to this spec;
    - the open-questions row "Edit in place, or supersede with a new ID?".
  - `docs/architect/foundations/ai-assisted-threat-modeling.md`, step 5 ("Edits follow the
    register's rule: edit in place, logged, then re-review"). It now says that AI edits go back to
    re-review and that the reviewer's own logged edits keep the approval. The playbook's word
    range and page contract still hold.
  - `docs/process/08-document/threat-register.md` (the "Never lose history" habit). It is general
    advice for any team, so the intent is this: a row changed by anyone other than an approver,
    an AI drafter in particular, goes back to review until it is re-approved, while an approver's
    own logged edit keeps the approval. The exact wording is the builder's, within the page's
    contract.

## 10. Left to the builder

Exact package versions, file layout inside `webapp/`, component structure, the default port,
styling within Mantine's defaults, error wording beyond core's messages, how the dev server
proxies to the back end (production rules must not weaken; dev mode only behind an explicit flag),
and how the tests are organized.

## 11. Later

A per-approval proof of the human (Touch ID through WebAuthn, or the signed approvals of
`webapp/DESIGN.md` section 5); more than one reviewer, with accounts; creating systems and the
legacy import in the browser; editing `dfd.md` in the browser.
