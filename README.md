# Threat models

A local risk registry for threat models, built on the standard library only. No AI is needed to use
it. Every system has a DFD, a register of risks, and a threat model document under `systems/<slug>/`.
Methods come from the sibling [threat-model-framework](../threat-model-framework) guide.

## Quick start

Requires Python 3.11 or newer (`python3 --version`).

```bash
./tmreg --help
make test                  # run the unit tests
./tmreg verify ordering-platform
```

Edit `project.toml` first: set `reviewer_name` and `reviewer_email` to your own. Every review is
recorded under that identity.

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
| `edit` | `./tmreg edit ordering-platform T-01 --set status=accepted` |
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
2. Add risks yourself (`./tmreg add <slug> --template`) or let a modeling run draft them. Every new risk is `pending`.
3. `./tmreg review <slug>` walks the pending risks one at a time; approve, reject, or edit each.
4. `register.md` is regenerated after every write. Never hand-edit it; commit it with the database.
5. Existing risks change through `edit` (which sends an approved risk back to review), `merge`, or `retire`.

## Reports, verify, and trial runs

- `./tmreg report <slug>` renders approved risks as `md` (default), `csv`, or `html`. Add
  `--include-pending`, `--include-rejected`, or `--include-retired` to widen it; `--out PATH` writes a file.
- `./tmreg verify <slug>` replays the change log and checks its hash chain and the stored rows.
  Run it after any import and before relying on a report.
- Trial runs: add `--trial` to try the workflow without touching the real register.
  `./tmreg init-system trial-sys --name "Trial" --trial` creates a system in `registry/trial.db`
  (git-ignored). Trial runs write `register.trial.md` and run IDs starting `trial-`.

## What the guard blocks

Claude Code may draft risks and DFD changes in this project, but it may not approve anything or
change the registry. Four layers enforce this. The first three block, and the fourth detects what
gets past them.

1. **Human-only commands need a terminal.** `review`, `approve`, `reject`, `merge`, `retire`,
   `import-legacy`, and `dfd approve` refuse to run without an interactive terminal. Claude Code's
   shell has none, and no flag or environment variable bypasses the check.
2. **The hook** (`.claude/hooks/guard.py`, a `PreToolUse` hook) is an allow-list. It runs before
   every Bash, Monitor, Edit, Write, MultiEdit, and NotebookEdit call, and it blocks everything it
   does not name.
   - **Commands.** Each call is one plain command, with no shell operators, quotes, globs, `$`,
     redirection, or line breaks. It must be one of these:
     - `./tmreg` with `list`, `show`, `history`, `report`, `verify`, `runs`, `add`, `edit`,
       `dfd status`, `dfd check`, or `run start`. Only that subcommand's own options are allowed,
       spelled in full. `--db` and `--out` are refused, as are their abbreviations, because they
       would point tmreg at another database or write a file anywhere. For `add` and `edit`,
       `--json` must name a `.json` file under `systems/<slug>/runs/<run-id>/`, and `--set` is
       refused, so every AI write leaves its file in the run record.
     - `git status`, `git diff`, or `git log`, without `--output` or `--ext-diff`.
     - `ls`.

     Everything else is blocked. That includes the human-only and other tmreg subcommands, other
     ways of starting tmreg (`tmreg`, `python3 -m tmreg`), interpreters and scripts, terminal
     wrappers that fake a TTY (`script`, `expect`, `unbuffer`), `sqlite3`, and git commands that
     roll files back.
   - **Files.** Edit, Write, and MultiEdit may write only `systems/<slug>/dfd.md` and `.md` or
     `.json` files under `systems/<slug>/runs/<run-id>/`. Paths are checked after symlinks are
     resolved. NotebookEdit is always blocked. Other tools, such as Read, Grep, and Glob, pass.
   - **Fails closed.** A malformed call, a missing project root, or an error inside the guard blocks
     the call. If the guard cannot run at all, `"onFailure": "block"` in the settings blocks the
     call instead.
3. **Permission rules** (`.claude/settings.json`) are a second layer behind the hook.
   - The allow rules pre-approve exactly the commands and writes above, so Claude is not slowed by
     prompts.
   - The deny rules cover the human-only subcommands, the other ways of invoking tmreg, terminal
     wrappers, inline interpreters, `sqlite3`, and git `checkout`, `restore`, `reset`, and `stash`.
     They also deny edits to `registry/`, `.claude/`, `systems/*/register.md`, `tmreg`,
     `project.toml`, and `CLAUDE.md`. A deny rule beats any allow rule.
   - Deny rules apply right away. The allow rules, and the read access to the guide in
     `additionalDirectories`, apply only after you accept the workspace-trust dialog for this
     folder.
4. **Detection.** `./tmreg verify <slug>` checks the change log's hash chain and its triggers. It
   also replays the log and compares the result with the stored rows, so an edit made outside
   tmreg shows up. `/tm-model` runs it first and stops on a failure.

**Limits.**
- These controls stop Claude, and anything else run non-interactively, from approving through any
  path known when they were built. They also make out-of-band edits detectable.
- They are not proof against a model actively looking for a new way around them, for example after
  a prompt injection in `inputs/`.
- They are not a defense against a malicious local user.
- The hook checks only the tools named above. A tool it does not name, such as an MCP server tool
  that writes local files, is not checked, so do not enable such a server for this project.
- The upgrade path, which is not built, is signed approvals: each approval is signed with the
  reviewer's SSH key, and the registry rejects an approved row without a valid signature.
  `webapp/DESIGN.md` section 5 describes it.

## Maintaining tmreg

The hook and the deny rules on `registry/**` and `.claude/**` stop Claude from changing the tool
itself, even in a session you start for that purpose. A deny rule cannot be overridden by an allow
rule anywhere, so lifting the guard means editing the settings file by hand. Use this flow for any
change to `registry/`, the guard, or the settings:

1. Start from a clean working tree (`git status`).
2. In your own editor, edit `.claude/settings.json`: remove the `hooks` entry and the
   `Edit(/registry/**)` and `Edit(/.claude/**)` deny rules. Remove only what the change needs.
3. Start `claude` and make the change. Keep the session to that change.
4. When the session ends, restore the guard in your own terminal:

   ```bash
   git checkout .claude/settings.json
   ```

   Only you run this, because the deny rules block `git checkout` for Claude. If the change needs
   a new rule in the settings, add it by hand after restoring.
5. Run `make test` and `./tmreg verify <slug>` for each system, review the diff, and commit.

There is also a one-session switch that writes no file: `claude --settings '{"disableAllHooks": true}'`
turns off every hook for that session only. It also turns off any status line, and it cannot turn
off one hook alone. It leaves the deny rules in force, so it is not enough to change `registry/` or
`.claude/`. Use the hand-edit-and-restore flow above for tmreg maintenance.
