# Web app design template (not built)

A design for a future web app that makes the risk registry easier to view and edit. Nothing here is
built. The three mockups in `mockups/` are static pages with sample data from the reference
catalog; open them in a browser to see the intended layout, including at phone width and in dark
mode.

## 1. Purpose and rules

The app is a second front end to the registry, next to the `./tmreg` CLI. It exists to make
reading and editing registers easier, not to change what the registry allows.

- **All rules live in `registry/tmreg/core.py`.** The server is a thin layer: it parses a request,
  calls one `Registry` method, and renders the result or the `RegistryError` message. It
  validates nothing itself, so the CLI and the web app cannot disagree.
- **No select-all.** No checkbox, button, or keyboard shortcut selects more than one risk.
- **No multi-item endpoint.** Every write route names exactly one system and at most one risk ID
  in its path. There is no approve-all, no batch reject, no bulk retire.
- **No approve without a note.** The Approve and Reject buttons are inert until the note field
  has text, and core refuses a note under 20 characters regardless of what the page does.
- **Approve only what was shown.** Core takes a keyword-only `seen` dict on `approve`, `reject`,
  `merge`, and `retire` and raises `StaleRecord` ("changed since it was shown; review it again")
  if the row changed. The web app must always pass it (see section 4).
- **Every create lands pending.** Adding a risk in the UI calls `add_risk`, so a risk added by
  hand still goes through the review queue.

## 2. Screens

All screens are scoped to one system, chosen with the system switcher in the header. No screen
mixes systems, matching the registry (no API spans two systems).

| Screen | What it shows | Mockup |
|---|---|---|
| Register | Tabs: Approved, Pending review, Rejected, Retired (each with a count). Filters on status, element, category, and origin. Columns: ID, title, elements, category, status, origin. Buttons: Add risk, Report. Row actions: Open, Edit, Retire (approved rows only). | `register.html` |
| Risk detail | Every risk field, grouped; the duplicate flag with Merge and Keep separate; the risk's change history; Edit and Retire. | `risk-detail.html` |
| Review queue | One pending item at a time, previous and next, a required note, Approve and Reject, the re-review diff, the duplicate flag, and the "DFD has moved on" banner. | `review-queue.html` |
| History | The per-system change log: sequence number, time, actor, operation, row, with the hash-chain check result. | not mocked |
| DFD approvals | Current `dfd.md` status (none, current, changed), the approval list, a preview of added and removed IDs with warnings, and Approve DFD with a note. | not mocked |
| Reports | Format (md, csv, html) and three include toggles (pending, rejected, retired); shows the output. | not mocked |

The Pending review tab links to the review queue; it never offers a way to act on its rows from
the table. The only place a risk is approved is the review queue, one item at a time.

## 3. Actions

One row per UI action that calls core. "Takes" is the risk IDs the call accepts: one at most. Merge
also names the live risk the pending one folds into, as a parameter; only the pending risk changes
state. Keep separate is not a row because it makes no call: the duplicate flag is data, and the
reviewer simply goes on to Approve or Reject.

| UI action | Core function | Takes | Notes |
|---|---|---|---|
| Open register tab | `Registry.list_risks` | none | `state` is `approved`, `pending`, or `rejected`; the Retired tab is `approved` rows with status `retired`, filtered in the server. Filters on status, element, category, and origin run over the returned list. |
| Open risk detail | `Registry.get_risk` | one risk ID | Also keep the row as the `seen` value (section 4). |
| Risk change history | `Registry.history` | one risk ID | |
| System change log | `Registry.history` | none | Same method, no ID. |
| Add risk | `Registry.add_risk` | none (ID allocated by core) | Lands pending. |
| Edit risk | `Registry.edit_risk` | one risk ID | Editing an approved risk sends it back to pending with a re-review diff. |
| Approve | `Registry.approve` | one risk ID | Needs note and `seen`. |
| Reject | `Registry.reject` | one risk ID | Needs note and `seen`. In a re-review it restores the last approved version. |
| Merge duplicate | `Registry.merge` | one risk ID (the pending one) | Needs note and `seen`. Core refuses a re-review. |
| Retire | `Registry.retire` | one risk ID | Needs a reason (20 characters or more) and `seen`. |
| DFD status | `Registry.dfd_status` | none | |
| DFD preview | `Registry.dfd_preview` | none | Added and removed IDs, and risks citing removed IDs. |
| Approve DFD | `Registry.dfd_approve` | none | Needs a note. Human-only like the rest. |
| Legacy import preview | `Registry.import_preview` | none | Writes nothing. |
| Legacy import | `Registry.import_legacy` | none | One-time, human-confirmed, after the DFD is approved. |
| Report | `Registry.report` | none | `fmt` and the three include flags. |
| Verify | `Registry.verify` | none | Shown on the History screen. |

## 4. Review queue behavior

- **One item at a time.** The queue is `list_risks(slug, "pending")` in ID order. The page shows
  position ("2 of 5"), Previous, and Next. Previous and Next only navigate; they write nothing.
  There is no list view with row actions and no "approve and next" that skips the note.
- **Required note.** A text area above the buttons. Approve and Reject are disabled until it has
  text. Core still enforces the 20-character minimum and the page shows core's message.
- **Stale records.** The page for a pending risk embeds the record exactly as displayed, from
  `get_risk`, as a hidden field. Approve, Reject, and Merge post it back, and the server passes it
  unmodified as `seen=`. Core compares the fields under its write lock. On `StaleRecord` the
  server writes nothing, re-reads the row with `get_risk`, re-renders the page with the current
  version and a banner ("This risk changed after you opened it. Review the current version."),
  and keeps the typed note in the box. The reviewer must press Approve again on what they now see.
  The server must never retry the call with a refreshed `seen` on its own.
- **Re-review diff.** When a pending risk has `last_approved`, the page shows a field-by-field
  table: field, last approved value, proposed value, with unchanged fields collapsed. Reject
  restores the last approved version (core's `revert`), and the button label says so.
- **Duplicate flag.** When `possible_duplicate_of` is set, the page shows that risk beside the
  draft with two choices: Merge (calls `merge`, the pending risk is rejected with `merged_into`)
  and Keep separate (no call; the reviewer goes on to approve or reject on the merits). Merge is
  not offered on a re-review.
- **"DFD has moved on" banner.** Shown when `dfd_status` is `changed`: the draft was written
  against an earlier approved DFD (`dfd_approval_id` on the row) and `dfd.md` has since
  changed. The banner links to DFD approvals and does not block review; it tells the reviewer
  the element IDs may be out of date.
- **After a decision.** The page returns to the next pending item, or to an empty-queue message.

## 5. Signed approvals (upgrade path)

Not built; this is how the web build could close the gap that option A of the approval lock
leaves open (a process that can reach core cannot be told apart from a human).

- **Payload.** The canonical JSON (sorted keys, no whitespace, UTF-8) of
  `{system, risk_id, content_sha256, reviewer, at, note}`, where `content_sha256` is the hash of
  the canonical JSON of the risk's content fields as approved.
- **Signing.** `ssh-keygen -Y sign -n tmreg-approval` over the payload, using a key held in an
  agent added with `ssh-add -c`. The `-c` flag makes the agent ask for confirmation on every use,
  so each approval raises a dialog only the human at the keyboard can click.
- **Verification.** `ssh-keygen -Y verify` against an `allowed_signers` file that lists the
  reviewers' public keys, with the same `tmreg-approval` namespace.
- **Enforcement.** The registry rejects any approved row without a valid signature, and
  `verify` reports one as a problem. A row edited after approval no longer matches
  `content_sha256`, so the signature fails.
- **Web flow.** Approve builds the payload, asks the local agent to sign it (the dialog appears),
  and passes the signature to core with the note. No new rule is added to the UI.

## 6. Left open

- **Server stack.** Not chosen. Any stack that can call Python and render HTML works.
- **Authentication.** Local and single-user is assumed (bound to 127.0.0.1). SSO comes later.
- **Styling.** The mockups show structure and states, not a final look.
- **Core's terminal check.** `ReviewerSession` and the human-only operations require an
  interactive terminal, and a web server has none. The web build needs a deliberate, owner-reviewed
  change in `core.py` that replaces the terminal proof with something a web request can supply
  (for example the signed approval above) without letting a script create a session. That
  change is a core change, not a server shortcut.
