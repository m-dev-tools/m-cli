# Pre-commit integration

`m-cli` ships a [pre-commit](https://pre-commit.com) hook scaffold so
downstream M (MUMPS) projects can gate every commit on `m fmt --check`
and `m lint --error-on=fatal` without writing any boilerplate.

Three hooks are exported from `.pre-commit-hooks.yaml`:

| Hook id         | What it does                                                         |
|-----------------|----------------------------------------------------------------------|
| `m-fmt-check`   | Fails the commit if any staged `*.m` file is not already formatted   |
| `m-fmt`         | Rewrites staged `*.m` files in place to their canonical form         |
| `m-lint`        | Fails the commit on **fatal** lint findings (e.g. call-to-missing-label) |

Pick `m-fmt-check` *or* `m-fmt` — not both. The first blocks unformatted
commits; the second auto-fixes them.

## Two integration styles

### Style 1: pull from a published m-cli repo (recommended)

Once `m-cli` is published to a git host, downstream projects add this
to their `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/<owner>/m-cli
    rev: v0.1.0  # pin to a tagged release
    hooks:
      - id: m-fmt-check
      - id: m-lint
```

`pre-commit` clones the repo at `rev`, builds an isolated venv, and
runs the hooks against your staged `.m` files.

> **Note.** This style requires `m-cli` and its `tree-sitter-m`
> dependency to be installable from PyPI or git. Until that lands
> (see `TODO.md` and the m-cli README), use Style 2 below.

### Style 2: use a system-installed `m` (works today)

If your developers already have `m-cli` installed in their environment
(via `uv`, `pipx`, or `pip install -e ../m-cli`), you can wire pre-commit
to the system binary directly:

```yaml
repos:
  - repo: local
    hooks:
      - id: m-fmt-check
        name: m fmt --check
        entry: m fmt --check
        language: system
        files: \.m$
        types: [file]

      - id: m-lint
        name: m lint --error-on=fatal
        entry: m lint --error-on=fatal
        language: system
        files: \.m$
        types: [file]
```

`language: system` tells pre-commit to skip venv creation and assume
`m` is on `PATH`. Same result; no clone required.

## Tightening the lint gate

`m-lint` defaults to `--error-on=fatal` so it only blocks commits on
real bugs. To also fail on warnings (the SAC violations and the noisier
XINDEX rules), override the entry in your downstream config:

```yaml
  - repo: https://github.com/<owner>/m-cli
    rev: v0.1.0
    hooks:
      - id: m-lint
        args: ["--error-on=warning"]
```

(Note: `pre-commit` appends `args` after the hook's own `entry` line.
The default entry already supplies `--error-on=fatal`, and the override
arg simply takes precedence — `argparse` keeps the last value.)

## Running ad-hoc

You don't need pre-commit to use these checks:

```bash
m fmt --check Routines/         # exit 1 if anything would change
m lint --error-on=fatal Routines/  # exit 1 on fatal findings only
```

Both commands are designed to be CI-friendly: stable JSON / TAP /
text output, exit codes per [the standard convention][exit-codes], no
network dependencies.

[exit-codes]: https://github.com/<owner>/m-cli/blob/main/CLAUDE.md
