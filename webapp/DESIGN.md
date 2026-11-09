# Web app design notes

The web app is built. It is a second front end to the registry, next to the `./tmreg` CLI. This
file says what is built and keeps the upgrade path. The reasoning, the full screen descriptions,
and the API table are in `docs/superpowers/specs/2026-11-08-web-app-design.md`; this file points
there instead of repeating them.

The mockups in `mockups/` are static pages with sample data from the guide's reference system:
`register.html`, `risk-detail.html`, `review-queue.html`, and `review-full-record.html`. The last
one is the approved layout of the review page. Open them in a browser to see the layout, including
at phone width and in dark mode. The earlier three show structure only; the built screens follow
the spec.

## 1. Purpose and rules

The app makes reading and reviewing registers easier. It does not change what the registry allows.

- **All rules live in `registry/tmreg/core.py`.** The back end (`backend/tmweb/`, FastAPI) parses
  a request, calls one `Registry` method per request, and returns the result or the
  `RegistryError` message (422). It validates nothing itself, so the CLI and the web app cannot
  disagree. A `StaleRecord` returns 409 with the current record.
- **No select-all, no multi-item endpoint.** Every write route names one system and at most one
  risk ID in its path. There is no approve-all.
- **No approve without a note.** Approve and Reject stay disabled until the note meets the
  minimum, and core refuses a short note regardless of the page.
- **Approve only what was shown.** The page sends the record exactly as it received it as
  `seen`. On `StaleRecord` nothing is written, and the page shows the current record and keeps the
  note. Nothing retries on its own.
- **Every create lands pending.** Add risk calls `add_risk`.
- **The edit rule.** The owner's own edits keep the approval. AI edits (`--run`) send an approved
  risk back to review.

## 2. Screens

The front end (`frontend/`) is React, TypeScript, Vite, and Mantine. Every screen is scoped to one
system and one register (`main` or `trial`), and the register is part of every route and API path.
Screens: Register, Review (one pending risk at a time, with a re-review table, the duplicate flag,
the "DFD has moved on" banner, and a required note), Risk, Edit and Add, DFD, History with the
verify result, and Reports. Spec section 6 describes each one.

## 3. Actions

Each UI action calls one `Registry` method. The routes are in spec section 7. Writes are add,
edit (with `seen` and an optional reason), approve, reject, merge, retire, and approve DFD (with
the previewed `sha256`). Reads are the register lists, a risk and its history, the system history,
verify, the DFD with its preview, and reports. Report downloads go through the API client, which
sends the CSRF header, and are saved as a Blob; a plain link would get 401.

## 4. Starting the app and the lock

- `make web` (or double-click `start.command`) installs the pinned dependencies, builds the front
  end, and starts the server on `127.0.0.1`. It refuses to start without an interactive terminal
  or when `CLAUDECODE` is set. Restarting prints a new sign-in link.
- Sign-in is two parts. `/signin?token=...` works once and sets the `HttpOnly`, `SameSite=Strict`
  session cookie, then redirects to `/#k=<token>`. The front end stores that token in
  `localStorage`, removes it from the address bar, and sends it as `X-CSRF-Token` on every `/api`
  request. Cookies are shared across `localhost` ports, so the cookie alone opens nothing.
- Writes also need an `Origin` equal to the app's own. Any `Host` other than `127.0.0.1:<port>` or
  `localhost:<port>` is refused.
- Every response carries a Content-Security-Policy (the `CSP` constant in `backend/tmweb/app.py`).
  Every `/api` response is `Cache-Control: no-store`. Websockets are refused. The DFD page's
  readable view never loads images; it shows "Image not loaded: <alt>".
- `backend/tests/test_lock.py` walks every `/api` route and expects 401 without a session.
- `make test-web` runs the back end and front end tests.

The limit: a browser-automation tool in the signed-in browser can act as the owner. The README
says never to grant one access to `127.0.0.1` or `localhost`. Section 5 closes this later.

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

- **Per-approval proof.** The sign-in lock cannot tell the owner from a tool in the owner's browser.
  Signed approvals (section 5) or Touch ID through WebAuthn would.
- **Core's terminal check.** `ReviewerSession` and the human-only operations need an interactive
  terminal. The server passes it because it runs in the owner's Terminal window. A detached server
  fails closed.
- **More than one reviewer**, with accounts; creating systems and the legacy import in the browser;
  editing `dfd.md` in the browser.
