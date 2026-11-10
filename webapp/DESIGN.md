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
the "model has moved on" banner, and a required note), Risk, Edit and Add, Architecture, History
with the verify result, and Reports. Spec section 6 describes each one, except Architecture, which
`docs/superpowers/specs/2026-11-09-c4-model-design.md` describes (it replaced the DFD screen).

## 3. Actions

Each UI action calls one `Registry` method. The routes are in spec section 7. Writes are add,
edit (with `seen` and an optional reason), approve, reject, merge, retire, and approve the C4 model
(with the previewed `sha256`), and export the diagrams. Reads are the register lists, a risk and its
history, the system history, verify, the C4 model with its preview, the routes between two items,
and reports. Report downloads go through the API client, which
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
  Every `/api` response is `Cache-Control: no-store`. Websockets are refused. 
- `backend/tmweb/app.py` `DIAGRAMS_ROUTE` serves the diagrams. See section 4a.
- `backend/tests/test_lock.py` walks every `/api` route and expects 401 without a session.
- `make test-web` runs the back end and front end tests.

The limit: a browser-automation tool in the signed-in browser can act as the owner. The README
says never to grant one access to `127.0.0.1` or `localhost`. Section 5 closes this later.

## 4a. Architecture and diagrams

The Architecture page (`frontend/src/pages/ArchitecturePage.tsx`) shows the model status and the
approvals, the elements, paths, and trust boundaries in tables, the details and open-risk counts of
a selected item, the changes against the last approval, and a routes panel. Approve model sends the
previewed `sha256` as `expected_sha256`; a changed file returns 409. Routes are `GET
/api/{reg}/systems/{slug}/c4` and `.../c4/routes?from=&to=`, and `POST .../c4/approve` and
`.../c4/export`. All sit under `/api`, so the API lock covers them.

"Open diagrams" posts to `.../c4/export`. The server reads `workspace.dsl` once, checks it with
`c4.py`, and runs one Docker export of exactly those bytes (`backend/tmweb/diagrams.py`):

```
docker run --rm --name tm-c4-export-<sha12>-<hex16> --network none --cap-drop ALL
  --security-opt no-new-privileges --read-only --tmpfs /tmp --user <uid>:<gid>
  -v <repo>/diagrams/<reg>/<slug>/<sha256>.tmp-<hex16>/in:/usr/local/structurizr <pinned image>
  export -workspace workspace.dsl -format static -output site
```

- The image is `c4.STRUCTURIZR_IMAGE`, pinned by digest. A run that times out is removed with
  `docker rm -f`.
- The result is kept at `diagrams/<reg>/<slug>/<sha256>/`, once per file content. Only Structurizr's
  own verdict is kept. If Docker is down or fails, nothing is kept and the page shows why. The
  newest 5 exports per system and register are kept (`KEEP`), and an export in use is not pruned.
- `diagrams/` and every folder in it must be real folders, never links; otherwise the export is
  refused. `/diagrams` is git-ignored, and the git hooks refuse a link with that name.
- `/diagrams/{reg}/{slug}/{sha256}/{path}` (GET and HEAD) serves only `in/site/`. It has the same
  Host check and session cookie as `/api` (no CSRF header, since the browser opens it as a page).
  Responses carry `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`,
  `Cross-Origin-Resource-Policy: same-origin`, `Cross-Origin-Opener-Policy: same-origin`, and
  `Referrer-Policy: no-referrer`.
- The CSP for a diagrams file is the app's CSP with the export's inline-script hashes added to
  `script-src`. An export is accepted only if its inline scripts match
  `c4.EXPECTED_INLINE_HASHES`, the reviewed ones. After bumping the image, review the new viewer's
  scripts and update that constant.
- Docker is needed only here, and for `make test-c4`.

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
  `content_sha256`, so the signature fails. Under the edit rule the owner's own edit keeps the
  approval, so the owner's edits must be signed too, over the edited content.
- **Web flow.** Approve builds the payload, asks the local agent to sign it (the dialog appears),
  and passes the signature to core with the note. No new rule is added to the UI.

## 6. Left open

- **Per-approval proof.** The sign-in lock cannot tell the owner from a tool in the owner's browser.
  Signed approvals (section 5) or Touch ID through WebAuthn would.
- **Core's terminal check.** `ReviewerSession` and the human-only operations need an interactive
  terminal. The server passes it because it runs in the owner's Terminal window. A detached server
  fails closed.
- **More than one reviewer**, with accounts; creating systems and the legacy import in the browser;
  editing `workspace.dsl` in the browser.
