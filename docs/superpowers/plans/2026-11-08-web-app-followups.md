# Web App Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the deferred minors and parked findings from the web app build. Leave out the
items the owner held for a later DFD pass.

**Architecture:** These are small, independent fixes to the existing tmreg core, the FastAPI back
end (`webapp/backend/`), the React front end (`webapp/frontend/`), the docs, and the guide. They
come in five batches, one per task.

**Tech Stack:** As built: Python 3.11+ stdlib core; FastAPI and uv; React, TypeScript, Vite,
Mantine 9, react-router 8, TanStack Query 5, and Vitest.

**Spec:** `docs/superpowers/specs/2026-11-08-web-app-design.md`, which is binding. The original
plan's Global Constraints apply unchanged: `docs/superpowers/plans/2026-11-08-web-app.md`. The
item list comes from `~/Developer/threat-models-dev/web-app-followups.md`.

## Owner decisions (2026-11-08)

- **D1 (replaces ruling R7).** When the owner edits an approved risk and it keeps its approval,
  `dfd_approval_id` moves to the latest DFD approval only if the edit changes `elements`.
  Otherwise it stays, so "DFD has moved on" still shows when the risk was written against an older
  DFD.
- **D2.** `superseded-by-<ID>` statuses and custom method names stay terminal-only. Nothing is
  built for them.
- **Held for a later DFD-focused pass. Do not touch.**
  - DFD page readability.
  - "Added IDs: none" next to an empty list.
  - DfdPage pinning the file it showed.
  - The DFD endpoint reading the file twice.
- **Already fixed by the final fix wave.** No work needed:
  - 500s are logged.
  - The nested `<main>` and the second h1 are gone.
  - The README's CSP sentence and startup sentence are corrected.
  - Spec §7's intro and the §5.2 `#k=` removal are corrected.

## Global Constraints

- Every rule lives in `registry/tmreg/core.py`. The server and UI validate nothing themselves.
- tmreg stays stdlib-only. The guard is untouched, except where Task 5 verifies a frontmatter
  format.
- Stored and server-supplied text renders through `visible()`. No `dangerouslySetInnerHTML`
  except mermaid's SVG.
- Risk data never enters git. Use fixtures only. Never open the real databases or `project.toml`.
- Work on branch `feat/web-app-followups`. Stage files by name. Commit messages are `fix:` /
  `chore:` (guide: `content:` / `chore:`). Never push.
- Every task ends with `make test`, `make test-web`, and `cd webapp/frontend && npm run build`
  green. Task 5 also runs the guide's `make check`.

---

### Task 1: Registry and server robustness

**Files:**
- `registry/tmreg/core.py`
- `registry/tests/test_core_write.py`, `registry/tests/test_core_review.py`
- `webapp/backend/tmweb/__main__.py`, `app.py`, `errors.py`, `security.py`, `api_read.py`
- `webapp/backend/tests/`
- `webapp/frontend/vite.config.ts`
- the spec, §5.4 item 1

Items (each needs a test unless marked):
1. **D1.** In `edit_risk`'s human branch that keeps the approval, set `dfd_approval_id` to the
   latest approval only when `"elements"` is in the update. AI edits and edits of pending risks
   are unchanged. Tests:
   - an owner edit of `owner` keeps the old `dfd_approval_id` after a newer DFD approval;
   - an owner edit of `elements` moves it.

   Update spec §5.4 item 1 to say this.
2. **`editors(since_last_approval=True)`.** A human edit that leaves the row approved counts as a
   new approval baseline. It is not listed, and earlier edits are dropped.
   - Work out "left approved" by tracking `review_state` through the risk's change diffs from its
     `add` or `import`.
   - `since_last_approval=False` is unchanged.
   - Update the existing editors test in `test_core_review.py` on purpose. After approve → owner
     edit → AI edit, `since()` is `[ai]`.
   - The CLI's `show`/`review` output follows from this.
3. **Non-string `note`.** `edit_risk` with a non-string `note` raises `RegistryError("note must be
   text")`, not `AttributeError`.
4. **Unreadable `dfd.md`.** `dfd_status` guards `read_bytes()` with `OSError`. An unreadable file
   gives `current_sha256 None`. Test with `dfd.md` as a directory.
5. **Missing `project.toml`.**
   - `config.ConfigError`, raised from `load_project` in `/api/meta` and `/api/session`, maps to
     422 `{"detail": <message>}` through `errors.install`. It used to give a 500.
   - `Registry(...)` already wraps it as `RegistryError`.
6. **Front end not built.** When `static_dir/index.html` is missing, `/` and the SPA paths return
   503 with plain text: `The app's pages aren't built yet. Start it with webapp/start.command or
   make web.` They used to give a 500.
7. **Bind errors and `--port`.**
   - Only EADDRINUSE keeps the "port … in use" message. Any other bind `OSError` prints
     `tmweb: cannot listen on 127.0.0.1:<port>: <strerror>` and returns 1.
   - `--port` is validated as 1–65535 by argparse, so a bad port is an argparse error, not an
     `OverflowError`.
8. **CSP on outer errors.** A 500 that escapes to Starlette's `ServerErrorMiddleware` still
   carries the `CSP` header (and `no-store` on `/api`). Register an `Exception` handler that
   builds that response with the headers. Test it with a route that raises outside the lock's
   own catch, or by simulating that.
9. **Dev port.** `--dev` uses a dedicated port: Vite on `5199` with `strictPort: true`. Change
   `DEV_ORIGIN`, the printed dev link, and the `vite.config.ts` comment to match. There is no
   production change.

### Task 2: Review page polish

**Files:** `webapp/frontend/src/pages/ReviewPage.tsx` (+ test),
`src/components/review/*`, `src/components/manage/errors.ts`

1. **Background list-refetch error.** A list-refetch error (`risks.error`) replaces the page only
   when there is no data. Otherwise it shows a small Alert above the item and keeps the item and
   its note.
2. **Reloading indicator.** While the post-409 reload runs, the panel shows
   `Reloading this risk…`. The duplicate comparison and the element rows are hidden until the
   reload reconciles.
3. **`reloadFailed` resets.** A later successful fetch clears it. Its message shows inside the item
   rather than behind the `fetched.error` early return.
4. **Offline guard.** After a 409, buttons re-enable only when the risk query's `dataUpdatedAt` has
   advanced past the 409.
5. **R15 fallback.** When `?id=` names a risk that is not pending, pin the shown id into the URL
   with `replace`, the same as with no id.
6. **409 without `current`.** Show the banner, refetch, and reconcile, the same as the 409 path.
7. **Escape errors.** `risks.error.message` and `fetched.error.message` render through `visible()`.
8. **History refresh.** The post-409 reload also refetches the risk's history.
9. **Pluralize.** `1 other field unchanged` / `<n> other fields unchanged`.
10. **One stale banner string.** `STALE_TEXT` lives only in `components/manage/errors.ts`.
    ReviewPage imports it.
11. **Note counter.** It counts code points (`[...note.trim()].length`), matching core. The same
    goes for the RetireModal counter.
12. **Test pin:** Previous/Next drops the note between items.

### Task 3: Other pages and shell

**Files:** `src/components/AppShell.tsx` (+ `.module.css`, test), `src/pages/*`,
`src/components/record/*`, `src/components/manage/*`, `src/main.tsx`, `public/favicon.svg`,
`webapp/backend/tmweb/app.py` (favicon route) and its test

1. **Navbar closes on every navigation.** Close it on any location change (pathname or search),
   not only on nav-link clicks.
2. **Collapsed-navbar visibility rule.** Use `(width < $mantine-breakpoint-sm)`, which closes the
   band at exactly 768px. Correct the CSS comment.
3. **Sticky rail.** Give it `max-height: calc(100vh - <header>)` and `overflow-y: auto`, so the
   decision buttons are reachable on short screens. In trial, the decision panel and the risk
   action panel also show a small `Trial register` badge.
4. **Element caption once.** Show it only once in section 2 (in the heading, as the mockup does).
5. **`last_approved` copy.**
   - pending with null: `None (new draft)`;
   - approved or rejected with null: `None (no re-review pending)`;
   - otherwise as now.

   The score stays as stored; do not add "of 9".
6. **Flow cell.** A null `from` or `to` renders as `?` instead of an empty string. No leading
   space.
7. **ElementTable on `dfd.error`.** Each row reads `DFD details unavailable` instead of `Not in the
   current DFD`.
8. **Register tabs.** Use `Tabs.Panel` (or drop the panel ARIA wiring) so `aria-controls` points at
   a real element.
9. **Metadata error.** A `useMeta` error shows an Alert on RegisterPage and RiskPage instead of
   spinning forever.
10. **Shared layout.** RiskPage's layout CSS moves to a shared layout module that ReviewPage and
    RiskPage both import. No cross-folder import from `components/review`.
11. **Cancel stays in the app.**
    - edit: go to the risk page, or to `review?id=` when `?return=review`;
    - add: go to the register.
12. **Modal titles.** `risk.id` in the modal titles and confirmation text goes through `visible()`.
13. **Modals on a 409 without `current`.** Show the banner, invalidate, and adopt the refetched
    risk as `seen` when it arrives. Test it.
14. **Home.** `Could not load systems: …` goes through `visible()`.
15. **Startup.** `main.tsx` renders after `initCsrf()` in `.finally(...)` so a rejection still
    renders the app.
16. **Favicon.**
    - Replace the Vite logo with a simple neutral shield SVG, written inline in the file.
    - The back end serves `/favicon.svg` from `static_dir` as `image/svg+xml`. Only that exact file
      name is served; no other root files.
    - Test: 200 with the right content type when the file exists.
17. **Refusal hint.** When a write's 422 `detail` contains `interactive terminal` or `--run`, the
    UI shows core's message, then a hint line: `The app may have lost its Terminal window. Close it
    and start the app again from webapp/start.command.`

### Task 4: Tests and tidying (no behaviour change)

**Files:** `registry/tests/*`, `registry/tmreg/dfd.py`, `webapp/backend/tests/*`,
`webapp/backend/tmweb/app.py`, `security.py`, `webapp/frontend/src/**/*.test.*`,
`src/api/types.ts`, `src/routes.tsx`

1. **Edit-rule ordering tests (core).**
   - approved → AI edit → human edit stays pending, and `reject` restores the pre-AI snapshot;
   - approved → human edit → AI edit → `reject` restores the human version, with `verify == []`;
   - a run-less edit of an approved risk under `CLAUDECODE=1` is refused and leaves it approved.
2. **Missing assertions.**
   - `test_human_edit_of_approved_risk_keeps_approval` asserts `reviewed_at` is unchanged.
   - `test_approve_still_marks_detail_complete_after_ai_edit` asserts `verify == []`.
3. **`dfd.parse`.** Hoist the per-row `col` closure to a module function
   `_col(header, cells, *names)`.
4. **Approval ordering.** `test_dfd_approvals` covers DFD-1 and DFD-2 ordering. Include DFD-10 if
   cheap.
5. **Route walker.**
   - It fails on any route that is not an `APIRoute`, except the `/assets` Mount.
   - It fails on any `APIRoute` outside `/api`, except `/signin` and the SPA catch-all.
   - The floor counts routes, not method/path pairs.
   - Assert the SPA catch-all is registered last.
   - `test_spa_fallback` also checks that `GET /api/session` gives 200 with a `static_dir`.
   - `test_unhandled_error`'s `/api/boom` is added before the catch-all, or tested without a
     `static_dir`, with a comment saying why.
6. **Lock probes.** Pin the cases the reviewer probed by hand as tests:
   - Host missing; Host in upper case; Host with a trailing dot;
   - Origin missing on a write;
   - the dev origin allowed only with `dev=True`;
   - `token=` absent from stdout on both refusals.
7. **Small tidy-ups.**
   - `app.py` no longer imports the private `_same`; make it public in `security.py`.
   - `test_spa_fallback` has no function-level imports.
8. **Write API.**
   - `test_human_ops_fail_closed_without_terminal` is parametrized over all 7 write routes, and
     asserts history is unchanged.
   - `test_dfd_approve_and_stale_sha` asserts no new approval after the stale 409.
   - Pin R12: the same `seen` twice gives 409.
   - Rename the `_` loop variable in `test_reject_merge_retire`.
9. **Front-end tests.**
   - `visible()` covers a lone surrogate, U+2028, and U+200B.
   - The register row ID link is present with the right `href`, the keyboard path.
   - The EditRiskPage `?return=` test either exercises `?return=review` or is renamed.
10. **Lint and types.**
    - Fix the oxlint `only-export-components` warnings in `routes.tsx`, for example by moving
      helpers out.
    - Tighten `Risk` field types: `evidence: string | null`, `control_refs: string[] | null`, and
      `last_approved` as a typed snapshot or `Record<string, unknown> | null`, as documented.

### Task 5: Docs and the guide

**Files:**
- tool repo: the spec, and `.claude/commands/tm-model.md` only if Item 2 requires it;
- guide repo (branch `feat/ai-assisted-threat-modeling`):
  `docs/superpowers/specs/2026-11-07-ai-assisted-threat-modeling-design.md`,
  `docs/architect/foundations/ai-assisted-threat-modeling.md`

1. **Spec §5.2.** "Later starts skip what is already current" becomes: only `npm ci` is skipped
   when the lockfile hasn't changed.
2. **MCP denies in `disallowed-tools`.** Verify against Claude Code's documentation (claude.com
   docs, or the `claude-code-guide` agent's sources) whether command frontmatter
   `disallowed-tools` accepts server-level MCP names such as `mcp__claude-in-chrome`.
   - If it does not, use the documented form, for example `mcp__claude-in-chrome__*`, if one
     exists.
   - Otherwise leave the line, and add a one-line note in the README that the settings deny rules
     are what enforces it.
   - Report the source.
3. **Guide spec, old plan text.** Lines ~154 (the mockups tree note) and ~373 (signed approvals:
   "`webapp/DESIGN.md` and the playbook describe it") are updated to match the built app.
4. **Guide wording.**
   - Use one term consistently, the "reviewer's own edit", in the spec and the playbook.
   - Re-wrap playbook steps 6–7 to the file's line width.
5. **Restore playbook trims.** Put back "anywhere" in step 6 and "worksheets" in Artifacts. Keep the
   playbook within 700–1200 words by tightening elsewhere, with no lost citation, Verify marker or
   Decide item. Report the counts.
6. **Follow-ups file.** Update `~/Developer/threat-models-dev/web-app-followups.md`, which is
   outside the repo and not committed: mark each item done (with its task), held, or kept by
   decision.
