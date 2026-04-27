# m-cli — the M (MUMPS) source-level toolchain

`m fmt`, `m lint`, `m test` for the M (MUMPS) language. **Tier 1** of the M
ecosystem gap-remediation plan ([strategy doc](../m-tools/docs/m-tooling-tier1.md)).

Built on:
- **[m-standard](https://github.com/rafael5/m-standard)** — the language reference
- **[tree-sitter-m](https://github.com/rafael5/tree-sitter-m)** — the parser (99.06% clean on the 39,330-routine VistA corpus)
- **YottaDB** — open-source M engine; the test runner adapter targets YottaDB primarily, with the source-level tools (`m fmt`, `m lint`) engine-neutral

## Status

| Step | Tool | Status |
|------|------|--------|
| 1 | `m fmt` (formatter) | **Step 1.0 (identity round-trip) shipped** — 38,954 / 39,330 (99.04%) VistA routines round-trip byte-for-byte; 26 s on a current laptop |
| 2 | `m lint --logic` | Planned |
| 3 | `m test` | Planned (parser-aware port of `ytest`) |
| 4 | Single-test selection | Folded into `m test` |
| 5 | `m watch` | Planned |

## Install (development)

```bash
cd ~/projects/m-cli
make install      # uv sync --extra dev + pre-commit hooks
```

## Use

```bash
m --version                          # m-cli 0.1.0
m fmt path/to/routine.m              # rewrite in place
m fmt --check src/routines/          # CI mode: exit 1 if any file would change
m fmt --diff path/to/routine.m       # unified diff
m fmt --stdout single_file.m         # write to stdout
```

## Run the VistA round-trip gate

```bash
.venv/bin/python scripts/vista_round_trip.py \
    ~/vista-meta/vista/vista-m-host/Packages
```

Expected output: ~99.04% round-trip clean, parse errors in the
remaining ~0.96% match the [tree-sitter-m corpus boundary](https://github.com/rafael5/tree-sitter-m).

## Naming convention

Commands follow the universal `m <subcommand>` pattern (mirroring `cargo`,
`go`, `git`). The legacy `y*` shell tools in [m-tools/bin/](../m-tools/bin/)
are kept as references and templates only — they remain functional but
are not the canonical interface going forward.

## Layout

```
m-cli/
├── pyproject.toml              # uv-managed; tree-sitter-m as editable dep
├── src/m_cli/
│   ├── __init__.py
│   ├── cli.py                  # `m` dispatcher
│   ├── parser.py               # tree-sitter-m wrapper
│   └── fmt/
│       ├── __init__.py
│       ├── cli.py              # `m fmt` argparse + file orchestration
│       └── formatter.py        # the round-trip pretty-printer
├── tests/
│   └── test_formatter.py       # round-trip + idempotence + parse-error tests
├── scripts/
│   └── vista_round_trip.py     # full-corpus validation gate
└── README.md                   # this file
```

## Roadmap

Step 1 (this doc) ships the **identity formatter** — the full parse → emit
round-trip with no canonical-layout rules yet. Subsequent passes layer in:

1. **Indentation normalisation** — `; comment` lines, dot-block indentation, label-column-1 enforcement.
2. **Whitespace canonicalisation** — no spaces around `_` (string concat), single-space after commas, etc., per the M style guide.
3. **Vertical spacing** — blank `;` lines between sections.
4. **`--check` integration with pre-commit** — hook scaffold + reference config.
5. **VistA-corpus performance ceiling tightening** — target sub-30s, then incremental improvements as rules are added.

Each rule is added with: a hand-crafted test, a VistA-corpus regression
gate (cleanly-parsing routines must still round-trip with the rule
*disabled*; with the rule enabled, only intentional changes appear), and
a brief design note.

## Licence

AGPL-3.0, matching the YottaDB and `tree-sitter-m` licence posture.
