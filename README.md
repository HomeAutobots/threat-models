# Threat models

A local risk registry for threat models, built on the standard library only. No AI is needed to use
it. Every system has a DFD, a register of risks, and a threat model document under `systems/<slug>/`.
Methods come from the threat-model-framework guide, cloned beside this repo as
`../threat-model-framework`.

The guide ([HomeAutobots/threat-model-framework](https://github.com/HomeAutobots/threat-model-framework))
is private for now. `./tmreg` refuses to start until `framework_path` in `project.toml` points at a
checkout of it, because `import-legacy`, the `threat-model.md` skeleton, and `/tm-model` read the
guide's pages. Without the guide you can still read the code and run `make test`; the one test
that reads the guide's catalog is skipped. `systems/ordering-platform/dfd.md` is built from the
guide's reference system.

## Risk data stays out of git

The repository holds the tool and the reference system's DFD, never the risks. These are
created locally by tmreg and never committed:

- the databases (`registry/registry.db`, `registry/trial.db`, and any `*.db` or `*.sqlite`);
- generated registers (`systems/*/register.md`, `register.trial.md`) and anything you export;
- run records (`systems/*/runs/`), threat model documents (`systems/*/threat-model.md`), and
  inputs (`systems/*/inputs/`);
- every system's `dfd.md` except `systems/ordering-platform/dfd.md`.

Three layers keep them out:
- `.gitignore` covers them.
- `.githooks/pre-commit` refuses them even when forced with `git add -f`.
- `.githooks/pre-push` refuses any pushed commit that adds them, including one made with
  `--no-verify`.

`make test` installs the hooks (`make hooks` does it alone) and checks that nothing like this is
tracked. Keep exported reports (`./tmreg report … --out`) outside the repository.

The database lives only on your machine, so back it up, for example with Time Machine. To copy
it, copy `registry/registry.db` while no tmreg command is running. Run `./tmreg verify <slug>`
on any restored copy.

## Quick start

Requires Python 3.11 or newer (`python3 --version`), and the guide checked out beside this repo.

```bash
cp project.example.toml project.toml   # then set reviewer_name and reviewer_email
make test                              # installs the git hooks, runs the unit tests
./tmreg init-system ordering-platform --name "Ordering platform"   # creates registry/registry.db
./tmreg verify ordering-platform
```

## First run

`ordering-platform` is the guide's reference system. Its real register mirrors the guide's
threat catalog (`legacy_catalog` in its `system.toml`), so `/tm-model` runs on it use `--trial`;
tmreg refuses them otherwise. Do these steps in this order, in your own terminal unless a step
says otherwise.

1. Copy `project.example.toml` to `project.toml` (git-ignored) and set `reviewer_name` and
   `reviewer_email` to your own. Every review is recorded under that name.
2. Create the local register: `./tmreg init-system ordering-platform --name "Ordering platform"`.
   This writes `registry/registry.db`, `register.md`, and the `threat-model.md` skeleton, all
   git-ignored. Skip this step if `./tmreg verify ordering-platform` already prints `ok`.
3. Read `systems/ordering-platform/dfd.md`, then run `./tmreg dfd approve ordering-platform`.
4. Run `./tmreg import-legacy ordering-platform`. Do this only after the guide's branch is merged
   to `main` with a merge commit, so the guide commit cited in the import note stays reachable.
5. Run `./tmreg verify ordering-platform`.
6. Set up the trial register (`registry/trial.db`, git-ignored):

   ```bash
   ./tmreg init-system ordering-platform --name "Ordering platform" --trial
   ./tmreg dfd approve ordering-platform --trial
   ./tmreg import-legacy ordering-platform --trial   # skip this step for an evaluation run
   ```

   Without the trial import, the trial register is empty and the catalog is withheld, so the run
   shows what the model re-derives on its own. `run start` prints a note saying so.
7. In Claude Code, started in this folder: `/tm-model ordering-platform --trial <element IDs>`.
8. In your own terminal: `./tmreg review ordering-platform --trial`.

## Commands

Every command takes the system slug. `--trial` (after the subcommand) uses `registry/trial.db`
instead of the real database.

| Command | Example |
|---|---|
| `init-system` | `./tmreg init-system my-system --name "My system"` |
| `list` | `./tmreg list ordering-platform --state pending` |
| `show` | `./tmreg show ordering-platform T-01` |
| `history` | `./tmreg history ordering-platform T-01` |
| `runs` | `./tmreg runs ordering-platform` |
| `run start` | `./tmreg run start ordering-platform` |
| `dfd status` | `./tmreg dfd status ordering-platform` |
| `dfd check` | `./tmreg dfd check ordering-platform` (parses `dfd.md` and previews an approval; read-only) |
| `dfd approve` (human-only) | `./tmreg dfd approve ordering-platform` |
| `add` | `./tmreg add ordering-platform --template` |
| `edit` | `./tmreg edit ordering-platform T-01 --set status=accepted` (your own edit keeps the approval; an AI edit with `--run` sends an approved risk back to review) |
| `review` (human-only) | `./tmreg review ordering-platform` |
| `approve` (human-only) | `./tmreg approve ordering-platform T-37` |
| `reject` (human-only) | `./tmreg reject ordering-platform T-37` |
| `merge` (human-only) | `./tmreg merge ordering-platform T-38 --into T-12` |
| `retire` (human-only) | `./tmreg retire ordering-platform T-05 --reason "Component removed in 2026"` |
| `import-legacy` (human-only) | `./tmreg import-legacy ordering-platform` |
| `report` | `./tmreg report ordering-platform --format html --out report.html` |
| `verify` | `./tmreg verify ordering-platform` |

Human-only commands need an interactive terminal and refuse to run anywhere else.

## Review workflow

Run these in your own terminal.

1. Review `systems/<slug>/dfd.md`, then `./tmreg dfd approve <slug>`. Risks cite elements from the approved DFD.
2. Add risks yourself or let a modeling run draft them. Every new risk is `pending`. To add one
   yourself, run `./tmreg add <slug> --template > c.json`, edit the file, then run
   `./tmreg add <slug> --json c.json`.
3. `./tmreg review <slug>` walks the pending risks one at a time. For each one, you approve,
   reject, merge, skip, or quit. To change a risk, use `./tmreg edit`, which is a separate command.
4. `register.md` is regenerated after every write. Never hand-edit it. Like the database, it stays
   local and is never committed.
5. Existing risks change through `edit`, `merge`, or `retire`. Your own edits keep the approval,
   and AI edits (`--run`) send an approved risk back to review.

## Reports, verify, and trial runs

- `./tmreg report <slug>` renders approved risks as `md` (default), `csv`, or `html`. Add
  `--include-pending`, `--include-rejected`, or `--include-retired` to widen it; `--out PATH` writes a file.
- `./tmreg verify <slug>` replays the change log and checks its hash chain and the stored rows.
  Run it after any import and before relying on a report.
- Trial runs: add `--trial` to try the workflow without touching the real register. It uses
  `registry/trial.db` (git-ignored); step 5 of [First run](#first-run) sets up
  `ordering-platform` there. Trial runs write `register.trial.md` and run IDs starting `trial-`.

## Web app

A local web app for reading and reviewing the register. It calls the same `Registry` methods as
`./tmreg`, so the rules are the same. Design: `docs/superpowers/specs/2026-11-08-web-app-design.md`;
reference mockups: `webapp/mockups/`. It needs `uv` and Node.

- **Start it** in your own terminal: double-click `webapp/start.command`, or run `make web`. The
  first start installs the pinned dependencies and builds the front end; later starts skip what is
  current. It refuses to start in a Claude Code shell.
- **Sign in** with the one-time link the server prints in that window
  (`http://127.0.0.1:8765/signin?token=...`). The link works once. Restarting prints a new one.
- **Sign out** by closing the Terminal window. That stops the server and ends the session.
- **Main or Trial.** When `registry/trial.db` exists, the header switches between the two
  registers. A banner shows while Trial is selected.
- **Tests:** `make test-web` runs the back end and front end tests.

## What the guard blocks

Claude Code may draft risks and DFD changes in this project, but it may not approve anything or
change the registry. Four layers enforce this. The first three block, and the fourth detects what
gets past them. The web app has its own lock, described after the four layers.

The hook and the permission rules load only when Claude Code starts in this folder
(`~/Developer/threat-models`). A Claude session started anywhere else, such as the sibling guide
repo, is not guarded by them, even when it works on files here.

1. **Human-only commands need a terminal.** `review`, `approve`, `reject`, `merge`, `retire`,
   `import-legacy`, and `dfd approve` refuse to run without an interactive terminal. Claude Code's
   shell has none, and no flag or environment variable bypasses the check. They also refuse when
   `CLAUDECODE` is set and non-empty, even with a terminal. Claude Code exports that variable to
   every shell it starts, so a terminal wrapper run from a Claude session is refused too, in any
   folder. `add` and `edit` without `--run`, which record the write under your name, refuse there
   the same way. This check only adds a refusal. `env -u CLAUDECODE` evades it, which falls under
   the "actively looking for a new way around" limit below, and the terminal check still applies.
2. **The hook** (`.claude/hooks/guard.py`, a `PreToolUse` hook) is an allow-list. It runs before
   every Bash, Monitor, Edit, Write, MultiEdit, and NotebookEdit call, and it blocks everything it
   does not name.
   - **Commands.** A call must be one of these:
     - `./tmreg` with `list`, `show`, `history`, `report`, `verify`, `runs`, `add`, `edit`,
       `dfd status`, `dfd check`, or `run start`. Only that subcommand's own options are allowed,
       spelled in full. `--db` and `--out` are refused, as are their abbreviations, because they
       would point tmreg at another database or write a file anywhere. For `add` and `edit`,
       `--json` must name a `.json` file under `systems/<slug>/runs/<run-id>/`, and `--set` is
       refused, so every AI write leaves its file in the run record.
     - `git status`, `git diff`, or `git log`, without `--output`, `--ext-diff`, `--no-index`, or
       an order file (`-O`, `--order-file`), which can open files outside the repo.
     - A read-only command for searching and reading, alone or joined with `|`: `grep`, `rg`,
       `find`, `ls`, `cat`, `head`, `tail`, `wc`, `sort`, `uniq`, `cut`, or `file`.

     `./tmreg` and git calls are one plain command each, with no shell operators, quotes, globs,
     `$`, redirection, or line breaks. Read-only commands may also use single quotes, double
     quotes without `$`, backticks, `\`, or `!`, and a trailing `2>/dev/null` or `2>&1`, so
     patterns such as `'^## '` and `'token|secret'` work. Unquoted globs are still refused.

     Each read-only command may pass only its own search and display options (`READ_COMMANDS` in
     the guard). The list is an allow-list because in Claude Code's shell `grep` runs ugrep and
     `find` runs bfs, and options there run programs or write files: grep's `--filter` and
     `--save-config`, `rg --pre`, find's `-exec` and `-delete`, and `sort -o`, for example. Options
     that follow symlinks out of a folder (`grep -R`, `rg -L`, `find -L`) and the options that
     print or search binary files such as the registry database (`-a`, and rg's `-u`, whose third
     use searches binaries) are refused too. `grep -r` does not follow symlinks, and `rg
     --no-ignore --hidden` replaces `rg -uu`.
     Every path must be inside this project or a folder in `additionalDirectories` (the guide),
     after symlinks are resolved, and the registry databases are refused: read the registry with
     `./tmreg`. Relative paths resolve from the project folder, because `cd` is not allowed.

     Everything else is blocked. That includes the human-only and other tmreg subcommands, other
     ways of starting tmreg (`tmreg`, `python3 -m tmreg`), interpreters and scripts, terminal
     wrappers that fake a TTY (`script`, `expect`, `unbuffer`), `sqlite3`, `sed`, `awk`, `xargs`,
     and git commands that roll files back.
   - **Files.** Edit, Write, and MultiEdit may write only `systems/<slug>/dfd.md` and `.md` or
     `.json` files under `systems/<slug>/runs/<run-id>/`. Paths are checked after symlinks are
     resolved. NotebookEdit is always blocked. Other tools, such as Read, Grep, and Glob, pass.
     Some Claude Code versions have no Grep or Glob tool; the read-only commands stand in for
     them.
   - **Searching git-ignored files.** `inputs/`, `threat-model.md`, and every `dfd.md` except the
     reference system's are git-ignored, and Claude Code's `grep` skips git-ignored files when a
     search starts at or above the `.gitignore` that names them, as `rg` always does. Pass
     `--no-ignore-files` to grep and `--no-ignore` to rg to search them.
   - **Fails closed.** A malformed call, a missing project root, or an error inside the guard blocks
     the call. If the guard cannot run at all, `"onFailure": "block"` in the settings blocks the
     call instead.
3. **Permission rules** (`.claude/settings.json`) are a second layer behind the hook.
   - The allow rules pre-approve command prefixes and paths, including each read-only command, so
     Claude is not slowed by prompts. They are broader than the forms above: `Bash(./tmreg add:*)`
     matches any `add` command, and `Bash(grep:*)` any grep, for example. The hook narrows them to
     exactly those forms.
   - The deny rules cover the human-only subcommands, the other ways of invoking tmreg, terminal
     wrappers, inline interpreters, `sqlite3`, and git `checkout`, `restore`, `reset`, and `stash`.
     They also deny edits to `registry/`, `.claude/`, `webapp/`, `systems/*/register.md`, `tmreg`,
     `project.toml`, and `CLAUDE.md`. A deny rule beats any allow rule.
   - Deny rules apply right away. The allow rules, and the read access to the guide in
     `additionalDirectories`, apply only after you accept the workspace-trust dialog for this
     folder.
4. **Detection.** `./tmreg verify <slug>` checks the change log's hash chain and its triggers. It
   also replays the log and compares the result with the stored rows, so an edit made outside
   tmreg shows up. `/tm-model` runs it first and stops on a failure.

**The web app's lock.** The web app can approve, so its API is locked more tightly than a normal
local server. Every `/api` route needs two things, and without both the answer is 401:
- **The session cookie.** It is `HttpOnly` and `SameSite=Strict`. Cookies are shared across
  `localhost` ports, so another local server you open in the browser would receive it, and the
  cookie alone opens nothing.
- **The CSRF token in the `X-CSRF-Token` header.** Sign-in redirects to `/#k=<token>`. The fragment
  never reaches a server. The front end keeps the token in `localStorage` (per origin, so per port),
  removes it from the address bar, and sends it on every `/api` request, reads included. Report
  downloads go through the same client, so they carry it too.

Also:
- The server refuses to start without an interactive terminal or when `CLAUDECODE` is set, so a
  Claude Code shell cannot start it. The sign-in link is printed only in that window, works once,
  and is held in memory.
- It binds `127.0.0.1` and refuses any other `Host`, which blocks DNS rebinding. Writes also need an
  `Origin` equal to the app's own. There is no CORS, and no API key or stored password.
- Every response carries a Content-Security-Policy that allows only the app's own scripts, images,
  fonts, and connections. Every `/api` response is `Cache-Control: no-store`. Websockets are refused.
- Each write route names one system and at most one risk. There is no approve-all.
- `Edit(/webapp/**)` is a deny rule in `.claude/settings.json`, and the guard's allow-list already
  blocks starting the server and every command that makes web requests.
- `webapp/backend/tests/test_lock.py` walks every `/api` route and expects 401 without a session.

**Limits.**
- In a session started in this project, these controls stop Claude, and anything else run
  non-interactively, from approving through any path known when they were built. They also make
  out-of-band edits detectable.
- A Claude session started outside this folder loads neither the hook nor the permission rules.
  Only tmreg's own terminal and `CLAUDECODE` checks, and `verify`, still apply to it.
- They are not proof against a model actively looking for a new way around them, for example after
  a prompt injection in `inputs/`.
- They are not a defense against a malicious local user.
- The guard checks the words Claude sends, not what your shell turns them into. Claude Code's own
  wrappers (grep runs ugrep, find runs bfs) are covered by the option lists. An alias in your
  shell profile that points a read-only command at another program is not, and a zsh global
  alias (`alias -g`) expands anywhere in a command, so it could turn an allowed word into shell
  syntax. Keep global aliases out of the profile Claude Code's shell loads.
- The hook checks only the tools named above. A tool it does not name is not checked. That
  includes MCP tools that write local files or send data out, for example browser, mail, or drive
  connectors, so keep such servers off for this project. `/tm-model` disallows the built-in web
  tools (WebFetch and WebSearch) for its run, but not MCP tools.
- A browser-automation tool working in your signed-in browser, such as Claude in Chrome, can act
  as you in the web app. Never grant it `127.0.0.1` or `localhost`.
- The upgrade path, which is not built, is signed approvals: each approval is signed with the
  reviewer's SSH key, and the registry rejects an approved row without a valid signature.
  `webapp/DESIGN.md` section 5 describes it.

## Maintaining tmreg

The hook and the deny rules on `registry/**` and `.claude/**` stop Claude from changing the tool
itself, even in a session you start for that purpose. A deny rule cannot be overridden by an allow
rule anywhere, so lifting the guard means editing the settings file by hand. Use this flow for any
change to `registry/`, the guard, or the settings:

1. Start from a clean working tree with passing tests, and record the commit you start from:

   ```bash
   git status
   make test
   git rev-parse HEAD
   ```

   Write the printed sha down; step 4 restores from it.
2. In your own editor, edit `.claude/settings.json`: remove the `hooks` entry and the
   `Edit(/registry/**)` and `Edit(/.claude/**)` deny rules. Remove only what the change needs.
3. Start `claude` and make the change. Keep the session to that change.
   - Never stage or commit `.claude/settings.json` during the session, and do not let Claude do
     it. A plain `git checkout .claude/settings.json` restores from the index, so a staged lifted
     file would survive it, and a committed one would sit in `HEAD`.
   - Stage files by name, not with `git add -A`.
4. When the session ends, restore the guard in your own terminal from the recorded sha, and check
   the restore:

   ```bash
   git checkout <sha> -- .claude/settings.json
   git diff <sha> -- .claude/settings.json
   make test
   ```

   - The `git diff` must print nothing.
   - `make test` must pass. Its `test_settings.py` fails if the hook, `onFailure: block`, or a
     required deny rule is missing.
   - Only you run these, because the deny rules block `git checkout` for Claude.
   - If the change needs a new rule in the settings, add it by hand after the restore, then run
     `make test` again.
5. Run `./tmreg verify <slug>` for each system, review the diff, and commit.

There is also a one-session switch that writes no file: `claude --settings '{"disableAllHooks": true}'`
turns off every hook for that session only. It also turns off any status line, and it cannot turn
off one hook alone. It leaves the deny rules in force, so it is not enough to change `registry/` or
`.claude/`. Use the hand-edit-and-restore flow above for tmreg maintenance.

## License

MIT. See [LICENSE](LICENSE).
