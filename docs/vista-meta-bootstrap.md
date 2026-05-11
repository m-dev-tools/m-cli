---
created: 2026-05-10
last_modified: 2026-05-10
revisions: 1
doc_type: [HISTORY, EXPLAINER]
---

# vista-meta bootstrap — and why m-cli is independent of it now

This document records how the `vista-meta` YottaDB container was used during
m-cli's initial development, and why **m-cli is no longer dependent on it**.
It is reference material for archaeologists and the small subset of users
working specifically with VistA. **A new M developer with no MUMPS or VistA
background can ignore this entire document and use m-cli normally.**

## What `vista-meta` is

[`vista-meta`](https://github.com/rafael5/vista-meta) is a heavyweight
YottaDB + VistA + RPC-broker + FileMan + Octo-SQL Docker container. It was
built to study VistA itself; m-cli reused it during bootstrap because it
happened to be the easiest way to get a real YottaDB endpoint without a
host install, and because the VistA corpus it ships (the U.S. Department
of Veterans Affairs' VistA routines, ~40,000 files of pure ANSI MUMPS) is
the largest and most diverse open-source M codebase in existence.

## Why VistA was the bootstrap corpus

The four-tier strategy that m-cli executes ([m-tools docs](https://github.com/m-dev-tools/m-tools/blob/main/docs/m-tooling-tier1.md))
required validation against a real-world M corpus. The choice of *which*
corpus was driven by what existed at the time:

- **VistA was 39,330 routines of pure ANSI M in active production use for
  decades.** No comparable open-source M codebase existed.
- **The VA SAC / XINDEX rule set** — the only published, codified set of
  M-language quality rules — was originally written against VistA, so
  porting XINDEX (which became `m lint`'s first profile) required VistA
  source to validate against.
- **vista-meta was already running** on the maintainer's machine for
  unrelated VistA work. Reusing the engine cost zero additional infra.

What got bootstrapped against VistA, in order:

1. **The parser** ([`tree-sitter-m`](https://github.com/m-dev-tools/tree-sitter-m))
   reached 99.06% clean on the 39,330-routine VistA corpus. Every grammar
   rule that wasn't tested against VistA was suspect.
2. **`m fmt --rules=identity`** round-trip — 38,954 / 39,330 routines
   byte-identical. The 376 residuals matched the parser's corpus boundary
   exactly, so the formatter inherited the parser's correctness gate.
3. **`m fmt --rules=canonical`** — idempotency + AST-shape preservation
   verified over the full corpus.
4. **`m lint --rules=xindex`** — 42 of 66 XINDEX rules ported, validated
   against the same corpus (62,806 findings; 42 fatal — concrete missing-label
   bugs in routines like `A1BFJOBR.m`).
5. **`m test`** — initial smoke gate ran 11 m-tools test suites (224
   assertions) against VistA's YottaDB.
6. **`m coverage`** — label coverage byte-identical to VA's `ycover` tool
   on the m-tools test suites.
7. **`m lint` performance** — the 120 s budget for the full VistA corpus
   was the §3.5 validation gate. Three optimisation passes (1458 s → 166 s
   → 22.6 s) were measured on VistA.

Without VistA, none of these gates would have existed at the resolution
they did. That's the bootstrap value.

## What changed: the substrate moved

By 2026-04-27 (Tier 1 close), the development model had shifted:

- **VistA validates correctness** — but the day-to-day test loop doesn't
  need VistA.
- **The default test substrate became
  [`m-test-engine`](https://github.com/m-dev-tools/m-test-engine)** — a
  minimal `yottadb/yottadb-base` container with bind-mounted source at
  `/work` and `docker exec` as the transport. No SSH server, no FileMan,
  no Octo SQL. Cross-platform; spins up in seconds.
- **The default calibration corpus for non-VA rules became
  [`m-modern-corpus`](https://github.com/m-dev-tools/m-modern-corpus)** —
  modern, post-2010 M code from active open-source projects (EWD, mgsql,
  M-Web-Server, YDBOcto auxiliary, YDBTest). The `M-MOD-NN` rule track was
  calibrated against this corpus, not VistA.
- **The default lint profile changed from `xindex` to the curated M-MOD
  subset** after modern-corpus validation showed XINDEX's SAC legacy rules
  generate ~62 K findings on non-VA code (mostly from SAC mandates around
  lowercase variables/commands that aren't followed outside the VA).

What remains of vista-meta in m-cli is now purely **opt-in escape hatches**,
not dependencies — see the verification below.

## Independence verification

Concrete evidence that m-cli's default workflow does not require vista-meta:

### 1. No declared dependency

```bash
$ grep -i vista pyproject.toml
$        # (empty — zero matches)
```

`pyproject.toml` declares `tree-sitter-m` and `m-standard` as path-deps;
nothing vista-related is in `[project.dependencies]`,
`[project.optional-dependencies]`, or `[tool.uv.sources]`.

### 2. CI does not reference VistA

The
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) workflow clones
exactly two siblings — `tree-sitter-m` and `m-standard` — and runs
`uv sync`, `ruff check`, `mypy`, and `pytest --cov`. There is no VistA
clone, no vista-meta image, no SSH provisioning. CI is green on every
push, against fresh GitHub-hosted runners that have never seen VistA.

### 3. `make test` works without `~/data/vista-meta/conn.env`

The Makefile contract:

```makefile
VISTA_CONN := $(HOME)/data/vista-meta/conn.env
ifneq ($(wildcard $(VISTA_CONN)),)
include $(VISTA_CONN)
export VISTA_HOST VISTA_SSH_PORT VISTA_SSH_USER ...
endif
```

The vista-meta connection is **silently skipped** if the file is missing.
On a fresh clone with no `conn.env`, `make test` runs the pytest suite
end-to-end against the local Python environment — no engine required for
the unit tests, since `m_cli.engine` is mocked at the import boundary in
[`tests/conftest.py`](../tests/conftest.py).

### 4. Engine auto-detection prefers non-vista paths

[`m_cli.engine.detect_engine`](../src/m_cli/engine.py) resolves transports
in this order:

1. **Explicit override** via `M_CLI_ENGINE=local|docker|ssh`.
2. **vista-meta SSH** — *only if* `~/data/vista-meta/conn.env` exists
   (preserves the maintainer's existing setup; absent on every other
   machine).
3. **Local YottaDB** — if `mumps` is on `$PATH`.
4. **Docker via m-test-engine** — if a container named `m-test-engine`
   is running.
5. **`EngineNotConfigured`** with guidance pointing at all three paths.

A new M developer's first `m test` invocation hits path 3 or 4, never
path 2.

### 5. Default lint profile is non-VA

`m lint` with no `--rules` flag uses the curated M-MOD subset (26 rules).
The `vista` profile (8 VA-Kernel-specific rules — `OPEN`→`^%ZIS`,
`HALT`→`^XUSCLEAN`, `JOB`→TASKMAN, banner conventions, etc.) is
opt-in via `--rules=vista`. Without that flag, the linter behaves
identically on VA and non-VA code.

### 6. Corpus-validation scripts are corpus-agnostic

`make vista` / `make vista-canonical` / `make lint-vista` (in
[`Makefile.vista`](../Makefile.vista)) accept a `CORPUS=` argument. The
default in the main Makefile is the in-org `m-modern-corpus` so the gates
work on a fresh clone without VistA access. The historical name reflects
the original calibration substrate; the implementation is generic.

### 7. The `seed` / `unseed` / `test-vista` Makefile targets are opt-in

These wrap the legacy SSH-based vista-meta path for `@pytest.mark.vista`
tests (loading routines into a vista-meta container, running
vista-marker-decorated suites, then unseeding). They invoke
[`scripts/seed-vista.sh`](../scripts/seed-vista.sh) which exits cleanly
with `no conn file: $CONN — is vista-meta running?` when the file is
absent. Default `make test` does not invoke them.

## What remains, and why we keep it

These vista-related capabilities ship today and will continue to ship:

| Surface | Why kept |
|---------|----------|
| `vista` lint profile (`--rules=vista`)        | VA shops legitimately want VA-Kernel-specific rules. Profile is engine-aware and emits pure false positives outside VistA, so it must stay opt-in — but the rules themselves are real. |
| `xindex` lint profile (`--rules=xindex`)       | Engine-neutral subset of XINDEX (parse errors, dead labels, exclusive Kill, etc.). Useful against any M corpus, not just VistA. |
| SSH transport in [`engine.py`](../src/m_cli/engine.py) | Preserves the maintainer's vista-meta workflow; serves any user with a remote YottaDB reachable over SSH. |
| `make seed` / `make unseed` / `make test-vista` | Opt-in regression workflow for `@pytest.mark.vista`-decorated tests. |
| `scripts/vista_*.py` corpus drivers           | Corpus-agnostic; default to m-modern-corpus on fresh clones. |
| [`scripts/seed-vista.sh`](../scripts/seed-vista.sh) / [`unseed-vista.sh`](../scripts/unseed-vista.sh) | Templated SSH loaders for the `make seed`/`unseed` opt-in workflow. |

None of these are on the default install / build / test / lint / format /
publish path. A new M developer who clones m-cli, runs `make install &&
make test`, writes their first `*TST.m` suite, and ships their first PR
will not encounter any of them.

## TL;DR

VistA was the bootstrap calibration substrate because no other corpus of
that size and diversity existed. That phase is closed. Today m-cli
defaults to:

- **Engine:** [`m-test-engine`](https://github.com/m-dev-tools/m-test-engine)
  (minimal Docker YottaDB) or local `mumps` on `$PATH`.
- **Validation corpus:** [`m-modern-corpus`](https://github.com/m-dev-tools/m-modern-corpus)
  (post-2010 non-VistA M).
- **Lint profile:** curated M-MOD (engine- and dialect-neutral
  modernization rules).

VistA-specific affordances are kept as opt-in features for the users who
genuinely need them. The user-facing default path has no VistA assumption.
