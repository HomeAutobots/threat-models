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

Added when the guard is installed.
