# `m engine` Audit — 2026-05-13

A point-in-time, faithful snapshot of the `m engine` subcommand and every
action under it, as the binary ships today. Companion to
[`cli-output-audit-2026-05-13.md`](cli-output-audit-2026-05-13.md); this
document narrows the lens to one namespace and probes every verb and every
option exhaustively, including state transitions, exit codes, and error
paths.

For each action this document records, verbatim:

1. **What it does** — single-paragraph behaviour summary distilled from the
   driver source.
2. **`m engine <action> --help`** — verbatim, including bugs of omission.
3. **Real output** — captured `stdout`/`stderr` for the common shapes
   (idempotent paths, state-transition paths, error paths) with exit codes.
4. **Observations** — visual / UX notes for the refactor pipeline.

A final cross-cutting section pulls together patterns across the namespace.

---

## Audit environment

| Field            | Value                                                  |
| ---------------- | ------------------------------------------------------ |
| `m --version`    | `m-cli 0.1.0`                                          |
| Binary           | `/home/rafael/m-dev-tools/m-cli/.venv/bin/m`           |
| Driver           | `DockerDriver` (the only built-in)                     |
| Image            | `ghcr.io/m-dev-tools/m-test-engine:0.1.0`              |
| Container name   | `m-test-engine`                                        |
| Manifest         | `m-cli/dist/m-test-engine.json` (protocol 1, ydb r2.02)|
| Bind mount       | `$HOME/m-work` → `/m-work`                             |
| Source           | `src/m_cli/engine_cli.py`, `engine_driver.py`, `engine_manifest.py` |
| Date captured    | 2026-05-13                                             |
| Pre-run state    | container `m-test-engine` healthy                      |
| Post-run state   | container `m-test-engine` healthy (restored)           |

The audit drives the container through `status` → `version` →
`capabilities` → `logs` → `exec` (valid + bad) → `reset` (refusal only) →
`install` (idempotent re-pull) → `start` (running idempotent) → `restart`
(running → restart) → `stop` (running → stopped) → `stop` (idempotent
no-op) → `start` (stopped → running) → settle, capturing every distinct
output along the way. The destructive `reset --confirm` path is **not**
exercised; the manifest and driver source describe what it would do.

---

## Top-level `m engine`

### Source

`src/m_cli/engine_cli.py` builds the subparser tree; `engine_driver.py`
hosts `DockerDriver` (the only registered driver in core; out-of-tree
drivers register via the `m_cli_engines` entry-point group). The verb set
is hardcoded in `add_engine_arguments`; the manifest at
`dist/m-test-engine.json` carries an authoritative verb table that
**diverges** from the wired verbs (see Observation 6 below).

### `m engine` (no action, exit 0)

```
Lifecycle management for the canonical m-test-engine Docker container. Every verb shells out to docker / docker compose; configuration is driven by the vendored dist/m-test-engine.json contract. See `m doctor` for diagnostics with fix-pointers; `m engine status` is the single-line health summary.
Lifecycle management for the canonical m-test-engine Docker container.

USAGE
  m engine <action> [options]

COMMANDS
  status:        Print container/image/daemon state
  install:       Pull the canonical engine image (`docker pull`)
  start:         Start the engine container (compose-first; docker-run fallback)
  stop:          Stop the engine container (globals volume preserved)
  restart:       Stop + start
  logs:          Print container logs (use --follow to stream)
  shell:         Interactive bash shell inside the container
  exec:          Run a one-shot M command via `mumps -run %%XCMD`
  version:       Print manifest-declared vs container-reported versions
  reset:         DESTRUCTIVE: stop + remove + drop globals volume
  capabilities:  Emit the engine namespace's machine-readable capabilities (JSON)

Run 'm engine <action> --help' for more information about an action.
```

> **Visible bug:** the first two lines are near-duplicates. The first is
> `parser.description` (passed to argparse at creation); the second is the
> `tagline=` kwarg threaded into `print_overview(...)` (`engine_cli.py:170-176`).
> For every other gh-style overview in the CLI (`m`, `m ci`, `m stdlib`)
> those two strings carry **different** information; for `m engine` they
> say the same thing twice.

### `m engine --help` / `-h` (exit 0)

```
usage: m engine [-h] <action> ...

Lifecycle management for the canonical m-test-engine Docker container. Every
verb shells out to docker / docker compose; configuration is driven by the
vendored dist/m-test-engine.json contract. See `m doctor` for diagnostics with
fix-pointers; `m engine status` is the single-line health summary.

positional arguments:
  <action>
    status        Print container/image/daemon state
    install       Pull the canonical engine image (`docker pull`)
    start         Start the engine container (compose-first; docker-run
                  fallback)
    stop          Stop the engine container (globals volume preserved)
    restart       Stop + start
    logs          Print container logs (use --follow to stream)
    shell         Interactive bash shell inside the container
    exec          Run a one-shot M command via `mumps -run %XCMD`
    version       Print manifest-declared vs container-reported versions
    reset         DESTRUCTIVE: stop + remove + drop globals volume
    capabilities  Emit the engine namespace's machine-readable capabilities
                  (JSON)

options:
  -h, --help      show this help message and exit
```

> `exec`'s help text is `%XCMD` in `--help` but `%%XCMD` in the overview
> block — the percent-doubling is argparse-format escaping. (`%%` becomes
> `%` when argparse renders the metavar help, but the help= string for the
> verb is rendered verbatim by `_overview`. Two different render paths,
> same source string, different display.)

### `m engine bogus` (exit 2)

```
usage: m engine [-h] <action> ...
m engine: error: argument <action>: invalid choice: 'bogus' (choose from status, install, start, stop, restart, logs, shell, exec, version, reset, capabilities)
```

Plain argparse error, choices comma-list. Same shape as `m bogus-cmd`.

### Top-level `m capabilities` view (slice)

```json
"engine": {
  "purpose": "Manage the m-test-engine container (install/start/stop/...)",
  "options": [],
  "examples": []
}
```

The top-level capabilities manifest does **not** descend into engine
verbs. The complete machine-readable view requires running the namespace's
own verb: `m engine capabilities`.

---

## `m engine status`

### What it does

Builds an `EngineStatus` snapshot by running five `docker` probes:
`shutil.which("docker")`, `docker info`, `docker image inspect`,
`docker ps --filter`, and (when the container is up) `docker inspect
{{.State.Health.Status}}`. Returns **exit 0 if the container is running,
exit 1 otherwise** — for both `text` and `--json` output paths
(`engine_cli.py:207`). The exit semantics are not documented in `--help`.

### `m engine status --help` (exit 0)

```
usage: m engine status [-h] [--json]

options:
  -h, --help  show this help message and exit
  --json      Emit JSON
```

No description paragraph. No mention of exit codes. `--json` has a 9-char
hint.

### Text output (running, healthy, exit 0)

```
driver:           docker
image:            ghcr.io/m-dev-tools/m-test-engine:0.1.0
container:        m-test-engine
  cli installed:  ✓
  daemon up:      ✓
  image present:  ✓
  container up:   ✓
  healthy:        ✓
```

Three "header" rows (driver / image / container) flush left; five state
rows indented two spaces. Glyphs are `✓` (true) / `✗` (false) / `-` (None).

### Text output (running, healthcheck still in `starting`, exit 0)

Captured immediately after `m engine restart`:

```
driver:           docker
image:            ghcr.io/m-dev-tools/m-test-engine:0.1.0
container:        m-test-engine
  cli installed:  ✓
  daemon up:      ✓
  image present:  ✓
  container up:   ✓
  healthy:        -
```

The `-` glyph collapses two meanings: "no healthcheck declared" and
"healthcheck in `starting` state". The user has no way to distinguish.

### Text output (stopped, exit 1)

```
driver:           docker
image:            ghcr.io/m-dev-tools/m-test-engine:0.1.0
container:        m-test-engine
  cli installed:  ✓
  daemon up:      ✓
  image present:  ✓
  container up:   ✗
  healthy:        -
```

Same shape as the running case, with `container up: ✗` and `healthy: -`.
**Exit code 1** — only signal that the container is actually down.

### `--json` output (running, exit 0)

```json
{
  "driver": "docker",
  "installed": true,
  "daemon_reachable": true,
  "image_present": true,
  "container_running": true,
  "container_healthy": true,
  "image_ref": "ghcr.io/m-dev-tools/m-test-engine:0.1.0",
  "container": "m-test-engine",
  "image_labels": {
    "org.m-dev-tools.m-test-engine.bind-mount": "/m-work",
    "org.m-dev-tools.m-test-engine.image-rev": "e212fa2991ea4a8529f885fff6801b1fb1038750",
    "org.m-dev-tools.m-test-engine.protocol": "1",
    "org.m-dev-tools.m-test-engine.ydb-version": "r2.02",
    "org.opencontainers.image.created": "2026-05-11T18:46:01.163Z",
    "org.opencontainers.image.description": "Minimal YottaDB Docker container for m-cli + m-stdlib testing — replaces vista-meta for non-VistA work",
    "org.opencontainers.image.licenses": "AGPL-3.0",
    "org.opencontainers.image.revision": "e212fa2991ea4a8529f885fff6801b1fb1038750",
    "org.opencontainers.image.source": "https://github.com/m-dev-tools/m-test-engine",
    "org.opencontainers.image.title": "m-test-engine",
    "org.opencontainers.image.url": "https://github.com/m-dev-tools/m-test-engine",
    "org.opencontainers.image.version": "0.1.0"
  },
  "mismatches": []
}
```

### `--json` output (stopped, exit 1)

```json
{
  "driver": "docker",
  "installed": true,
  "daemon_reachable": true,
  "image_present": true,
  "container_running": false,
  "container_healthy": null,
  "image_ref": "ghcr.io/m-dev-tools/m-test-engine:0.1.0",
  "container": "m-test-engine",
  "image_labels": { ... full OCI labels block ... },
  "mismatches": []
}
```

> `m engine status --json` **does** propagate the exit-1 signal — verified
> directly: `m engine status --json > /dev/null; echo $?` → `1` when
> stopped, `0` when running. So the exit semantics are consistent across
> both render paths.

### Text/JSON parity

| Text row             | JSON key                               |
| -------------------- | -------------------------------------- |
| `driver:`            | `driver`                               |
| `image:`             | `image_ref`                            |
| `container:`         | `container`                            |
| `  cli installed:`   | `installed`                            |
| `  daemon up:`       | `daemon_reachable`                     |
| `  image present:`   | `image_present`                        |
| `  container up:`    | `container_running`                    |
| `  healthy:`         | `container_healthy` (`true/false/null`)|
| *(not shown)*        | `image_labels` *(JSON only)*           |
| *(not shown)*        | `mismatches` *(JSON only when empty)*  |
| `⚠ version skew…`   | `mismatches: [...]` *(non-empty path)* |

Text and JSON use **different** vocabulary for the same fields
(`cli installed` ↔ `installed`, `daemon up` ↔ `daemon_reachable`,
`container up` ↔ `container_running`). The `image_labels` block — 13 OCI
metadata fields — is JSON-only. Mismatches surface as a stderr-like `⚠`
block in text (not exercised in this audit), and as a plain list in JSON.

### Observations

- The exit-code semantic (`0 running / 1 not running`) is invisible to a
  user reading `--help`. CI authors who want a "is engine up?" boolean
  have to read the source.
- `--json` has no `image_labels` analogue in text — running the same
  command in two modes returns visibly different amounts of data.
- The `-` glyph for `healthy` is ambiguous (no healthcheck vs.
  healthcheck-still-starting). JSON returns `null` for both — same loss
  of fidelity.
- Indentation uses two-space "sub-rows" under three flush-left header
  rows — internally consistent, but a different visual idiom than
  `m doctor`'s flat tabular layout.

---

## `m engine install`

### What it does

`docker pull ghcr.io/m-dev-tools/m-test-engine:0.1.0` via the runner with
`capture=False` — output streams straight to the terminal from docker.
m-cli adds nothing.

### `m engine install --help` (exit 0)

```
usage: m engine install [-h]

options:
  -h, --help  show this help message and exit
```

Two-line `--help`. No description. No examples. No mention of disk-space,
network, or what an "idempotent re-pull" prints.

### Real output (idempotent re-pull, image already present, exit 0)

```
0.1.0: Pulling from m-dev-tools/m-test-engine
Digest: sha256:8346f73dd43dd7594b3ef6b3c68fa6e90ede2c7ef3b439f6d4d8619936dfa101
Status: Image is up to date for ghcr.io/m-dev-tools/m-test-engine:0.1.0
ghcr.io/m-dev-tools/m-test-engine:0.1.0
```

Pure passthrough from `docker pull`. No `m engine install:` prefix.
First-time install would show layered download progress (mb / Pulling fs
layer / Pull complete) — not captured here.

### Observations

- Zero m-cli synthesis. A user couldn't tell `m engine install` from
  running `docker pull …` directly except that they don't have to remember
  the image ref.
- A successful re-pull and a successful first install look completely
  different visually (progress bars vs three-line summary). Neither has a
  consistent m-cli message.

---

## `m engine start`

### What it does

Reads the container's current `docker inspect {{.State.Status}}` value.
Three branches (`engine_driver.py:403-415`):

1. State == `running` → print `container `m-test-engine` already running`
   (m-cli message), exit 0.
2. State exists but not running (`exited` / `created`) → `docker start
   m-test-engine` (passthrough), exit = subprocess return code.
3. No container at all → run the full `docker run -d --name … -v … image
   tail -f /dev/null` recipe from the manifest.

### `m engine start --help` (exit 0)

```
usage: m engine start [-h]

options:
  -h, --help  show this help message and exit
```

Two-line `--help`. No description.

### Real output

#### Already running (exit 0)

```
container `m-test-engine` already running
```

m-cli synthesized message, single line, backtick-quoted container name.

#### From `exited` state (exit 0)

```
m-test-engine
```

That's the entire output. The string `m-test-engine` is echoed by
`docker start` (which prints what it just started) — m-cli adds nothing.

#### From no-container (first-time install) state

Not captured in this audit (would require `m engine reset --confirm`
followed by `m engine start`). Would emit the `docker run` container-id
hash plus whatever the run pipeline streams.

### Observations

- **Three distinct output styles for the same verb** (m-cli message vs.
  `docker start` echo vs. unobserved `docker run` output). The user has
  to know docker conventions to know that `m-test-engine` is "what got
  started," not an error.
- The success path "container `m-test-engine` already running" is the
  only m-cli-synthesized message in the verb. Compare to `restart` (which
  always emits `restarted m-test-engine`).
- Single backticks around container name in the running-idempotent path
  — a unique glyph choice not repeated elsewhere in the engine namespace.

---

## `m engine stop`

### What it does

Reads `_container_state()`. If absent or already stopped → exit 0
silently. If running → `docker stop m-test-engine`. Globals volume is
preserved.

### `m engine stop --help` (exit 0)

```
usage: m engine stop [-h]

options:
  -h, --help  show this help message and exit
```

Two-line `--help`. No description.

### Real output

#### Running → stopped (exit 0)

```
m-test-engine
```

Pure passthrough from `docker stop` (which echoes the container name it
just stopped). No m-cli message.

#### Already stopped (exit 0)

```
(empty — silent no-op)
```

#### No container at all

Same as already-stopped: silent exit 0.

### Observations

- Three different success behaviours; only the "running → stopped"
  emits anything, and what it emits looks like a single random word.
- No "stopped m-test-engine" m-cli message to mirror `restart`'s
  `restarted m-test-engine`. Inconsistent with the sibling verb.
- Silent-exit-0 idempotent path means a script can't easily tell "I just
  stopped it" from "it was already down." (Use `m engine status` exit
  code for that.)

---

## `m engine restart`

### What it does

State-aware sequence (`engine_driver.py:431-458`):

1. If running: `docker stop` with captured output (errors propagated).
2. If state ≠ None: `docker start` (captured).
3. If no container: full `docker run` (uncaptured).
4. Always print `restarted m-test-engine` on success.

### `m engine restart --help` (exit 0)

```
usage: m engine restart [-h]

options:
  -h, --help  show this help message and exit
```

Two-line `--help`. No description. The top-level `--help` describes this
as "Stop + start" — terser than the docstring.

### Real output (running → restart, exit 0)

```
restarted m-test-engine
```

Single-line m-cli message. The intermediate `docker stop` / `docker
start` calls run with `capture=True`, so the bare container-name echoes
don't surface — unless one fails, in which case `result.stderr` prints
and exit code propagates.

### Observations

- The **only** verb that *always* emits a confirmation message, regardless
  of state path.
- `restart` and `start` (idempotent path) use sibling conventions
  ("restarted X" vs "container `X` already running") that are
  *almost* parallel but use different quoting / verb-conjugation forms.
- Captured stop+start outputs are dropped — by design, since the
  composite verb is the unit of work. Stderr from a failure does
  surface.

---

## `m engine logs`

### What it does

`docker logs m-test-engine` with `--follow` appended when the user passes
`--follow / -f`. Non-follow path captures output, then `print()`s it;
follow path streams unbuffered.

### `m engine logs --help` (exit 0)

```
usage: m engine logs [-h] [--follow]

options:
  -h, --help    show this help message and exit
  --follow, -f  Stream logs continuously
```

The only verb besides `status` that has the `-X` short alias documented
in --help (`-f`). No description.

### Real output (quiet container, exit 0)

```
(empty)
```

The manifest's `run_args.command` is `["tail", "-f", "/dev/null"]` — the
container's lifetime job is to do nothing visible. So `docker logs`
returns nothing on a healthy idle engine. A user who runs `m engine
logs` to "see what's happening" sees no signal.

### Observations

- The "empty is the success case" outcome is unobvious. There's no
  m-cli synthesis to confirm "logs read; container produced no output."
- `--follow` is one of three verbs that override the default capture
  behaviour (others: `shell`, `exec`). The streaming/blocking semantics
  are not advertised in the help text.

---

## `m engine shell`

### What it does

`docker exec -it m-test-engine bash` — interactive TTY into the
container. Not captured here (requires a TTY).

### `m engine shell --help` (exit 0)

```
usage: m engine shell [-h]

options:
  -h, --help  show this help message and exit
```

Two-line `--help`. No description.

### Observations

- Like `m lsp`, the verb is invisible to a non-interactive probe. No
  output to audit beyond `--help`.
- No documentation in `--help` of which user/UID, working directory,
  or shell rc files are loaded. (Driver code says `bash` with `-it`,
  which under the m-test-engine image's defaults sources
  `/etc/profile.d/ydb-env.sh`.)

---

## `m engine exec`

### What it does

`docker exec m-test-engine bash -lc '$ydb_dist/mumps -run %XCMD <quoted-cmd>'`.
The `m_cmd` arg is shell-quoted via `shlex.quote`. Bash's `-lc` ensures
profile.d scripts run so `$ydb_dist` is set. Exit code propagates
unchanged from YDB.

### `m engine exec --help` (exit 0)

```
usage: m engine exec [-h] m_cmd

positional arguments:
  m_cmd       M command to execute (e.g. 'write $ZVERSION,!')

options:
  -h, --help  show this help message and exit
```

One positional with an inline example. Description-less.

### Real output

#### `m engine exec 'write $ZVERSION,!'` (exit 0)

```
GT.M V7.1-002 Linux x86_64
```

Pure YDB output via the container.

#### `m engine exec 'set x=1 write x,!'` (exit 0)

```
1
```

#### `m engine exec 'this is not M'` (exit 186)

```
Error occurred: 150373050,%XCMD+5^%XCMD,%YDB-E-INVCMD, Invalid command keyword encountered
```

YDB's own error format (`Error occurred: <code>,<routine>,<%MNEMONIC>,
<message>`). m-cli adds no prefix, no friendly hint, no `m engine exec:`
wrapper. Exit code 186 is YDB's raw exit for "command parse error" — not
annotated.

#### `m engine exec` (no arg, exit 2)

```
usage: m engine exec [-h] m_cmd
m engine exec: error: the following arguments are required: m_cmd
```

Plain argparse error.

### Observations

- The success-output and error-output paths look completely different
  in size and format; both are pure YDB passthrough. The user has to
  parse YDB error vocabulary (`%YDB-E-INVCMD`, etc.) without help.
- Exit code 186 (and similar YDB-specific codes from other failure
  modes) are not surfaced in the output — a script reading `$?` after
  `m engine exec` gets ~5 distinct numbers depending on what failed.
- `m_cmd` is a single positional. To pass multi-command sequences with
  spaces or specials, the user has to quote correctly at the shell —
  no `--` separator documented or supported.

---

## `m engine version`

### What it does

Diffs the local manifest's three comparable fields (`protocol`,
`ydb-version`, `bind-mount`) against the OCI labels burned into the
pulled image. Also reads `org.m-dev-tools.m-test-engine.image-rev`
(advisory, no manifest counterpart) and the running container's
`docker inspect {{.Image}}` ID. Output: a side-by-side ASCII table with
✓/✗ per row. `--json` emits the same data as a structured record.

### `m engine version --help` (exit 0)

```
usage: m engine version [-h] [--json]

options:
  -h, --help  show this help message and exit
  --json      Emit JSON
```

Two-line description-less `--help`. The verb's top-level help says
"Print manifest-declared vs container-reported versions" — that's the
only authoritative documentation of what gets compared.

### Text output (all match, exit 0)

```
image:     ghcr.io/m-dev-tools/m-test-engine:0.1.0

                    manifest          image
                    ----------------  ----------------
  ✓ protocol          1                 1
  ✓ ydb-version       r2.02             r2.02
  ✓ bind-mount        /m-work           /m-work
    image-rev         (none)            e212fa2991ea4a8529f885fff6801b1fb1038750

container: image-id=sha256:8346f73dd43dd7594b3ef6b3c68fa6e90ede2c7ef3b439f6d4d8619936dfa101
```

Column widths: 16-char field name, 16-char manifest value, then image
value (no fixed width). `image-rev` has `(none)` in the manifest column
(literal text) and the un-truncated 40-char git sha in the image column.
The check-mark glyph in the leftmost column doubles as a separator;
`image-rev` has no glyph at all (it's advisory, not checked).

### Text output (mismatch path, not exercised)

From source (`engine_driver.py:570-583`):

- Each mismatching row gets `✗` instead of `✓`.
- After the table: `⚠ mismatch detected — run `m engine install` then recreate the container.`

(Hard to elicit without manually corrupting the manifest.)

### `--json` output (exit 0)

```json
{
  "image_ref": "ghcr.io/m-dev-tools/m-test-engine:0.1.0",
  "fields": [
    { "name": "protocol",    "manifest": "1",       "image": "1",       "match": true },
    { "name": "ydb-version", "manifest": "r2.02",   "image": "r2.02",   "match": true },
    { "name": "bind-mount",  "manifest": "/m-work", "image": "/m-work", "match": true }
  ],
  "image_rev": "e212fa2991ea4a8529f885fff6801b1fb1038750",
  "container_image_id": "sha256:8346f73dd43dd7594b3ef6b3c68fa6e90ede2c7ef3b439f6d4d8619936dfa101",
  "any_mismatch": false
}
```

### Text/JSON parity

| Text                     | JSON                       |
| ------------------------ | -------------------------- |
| `image: <ref>` header    | `image_ref`                |
| `✓ protocol`             | `fields[0].match=true`     |
| `✓ ydb-version`          | `fields[1].match=true`     |
| `✓ bind-mount`           | `fields[2].match=true`     |
| `image-rev` row          | `image_rev`                |
| `container: image-id=…`  | `container_image_id`       |
| `⚠ mismatch detected…`  | `any_mismatch: true`       |

JSON wraps the `name/manifest/image/match` quartet per field; text
collapses to ✓ + value. Functionally parallel.

### Observations

- This is the cleanest text format in the engine namespace: clear header
  row, dashed separator, ✓/✗ in column zero. Internally consistent.
- The em-dash glyph `—` appears in this table only in the unobserved
  no-label path (line 567: `display = "—"`), distinct from the `(none)`
  literal used when the manifest has no counterpart. Three different
  "missing value" idioms exist in this one table.
- `image-rev` is the only row without a check-mark glyph — visually
  inconsistent. It's advisory metadata, not a checked field.
- The 40-char sha in the image column overflows past the 16-char column
  width established by the header dashes, breaking column alignment.

---

## `m engine reset`

### What it does

Refuses without `--confirm` (exit 2). With `--confirm`:
`docker stop` → `docker rm` → `docker volume rm` for each named volume
in the manifest (`m-test-engine-globals`). After reset, the next
`m engine start` rebuilds the container with empty globals.

### `m engine reset --help` (exit 0)

```
usage: m engine reset [-h] [--confirm]

Wipes the running container AND the persistent globals volume. Useful when a
stuck global/lock state poisons tests. Refuses to run without --confirm.

options:
  -h, --help  show this help message and exit
  --confirm   Required acknowledgement that this is destructive
```

The **only** engine verb with a description paragraph in `--help`. The
description is precise: it names the side-effect (drops globals volume)
and the use case (stuck global state).

### Real output (no `--confirm`, exit 2)

```
refusing: `m engine reset` is destructive (drops the globals volume). Re-run with --confirm.
```

- Lowercase `refusing:` prefix — not `m engine reset: refusing:` and not
  capitalised.
- Backticked verb name embedded in the message.
- Exit code 2 (matches argparse-style "bad invocation" — same as `m`
  unknown-command, but here the invocation is well-formed; it's the
  policy gate that refuses).

### Real output (`--confirm`, not exercised)

From source: `docker stop` then `docker rm` then `docker volume rm` —
each with `capture=False`. So the user sees docker's raw output for each
step in sequence, no m-cli synthesis between them. Nothing prints on
success aside from `docker`'s own echoes (container name, volume name,
etc.).

### Observations

- The refusal message is the **only** engine-namespace error that uses
  the `refusing:` prefix (no other verb declines work). Distinctive
  vocabulary.
- The "destructive" property is carried in three places:
  - `dist/m-test-engine.json` — `"reset": { "destructive": true, … }`
  - `m engine capabilities` JSON — verbs[].destructive=true,
    requires_confirm=true
  - the runtime refusal — pure prose
  The three say the same thing in three forms; no obvious lint to keep
  them in sync.
- A user who passes `--confirm` to an already-stopped container sees a
  different sequence of docker echoes than one with a running container.
  Silent paths exist (already-removed container → `docker rm` returns
  non-zero, but error goes to stderr; m-cli doesn't intercede).

---

## `m engine capabilities`

### What it does

Hardcoded `print(json.dumps(payload, indent=2))` where `payload`
contains: the namespace name, the active driver name, a flattened
manifest snapshot, and a hand-written `verbs[]` array (11 entries) that
mirrors the argparse subparser registry — **not** the manifest's
`verbs` table (which has 13 entries).

### `m engine capabilities --help` (exit 0)

```
usage: m engine capabilities [-h]

options:
  -h, --help  show this help message and exit
```

Two-line description-less help.

### Real output (exit 0)

```json
{
  "namespace": "engine",
  "driver": "docker",
  "manifest": {
    "protocol": 1,
    "image": "ghcr.io/m-dev-tools/m-test-engine",
    "default_tag": "0.1.0",
    "image_ref": "ghcr.io/m-dev-tools/m-test-engine:0.1.0",
    "container": "m-test-engine",
    "ydb_version": "r2.02",
    "bind_mount": {
      "host": "/home/rafael/m-work",
      "container": "/m-work",
      "mode": "rw"
    }
  },
  "verbs": [
    { "name": "status",       "destructive": false, "read_only": true  },
    { "name": "install",      "destructive": false, "read_only": false },
    { "name": "start",        "destructive": false, "read_only": false },
    { "name": "stop",         "destructive": false, "read_only": false },
    { "name": "restart",      "destructive": false, "read_only": false },
    { "name": "logs",         "destructive": false, "read_only": true  },
    { "name": "shell",        "destructive": false, "read_only": false },
    { "name": "exec",         "destructive": false, "read_only": false },
    { "name": "version",      "destructive": false, "read_only": true  },
    { "name": "reset",        "destructive": true,  "read_only": false, "requires_confirm": true },
    { "name": "capabilities", "destructive": false, "read_only": true  }
  ]
}
```

### Observations

- The verbs list is **hand-maintained** in `_cmd_capabilities` — not
  derived from the argparse subparser tree, not derived from the
  manifest. Three sources of truth for "what verbs exist":
  1. `engine_cli.py` argparse registry (11 verbs wired).
  2. `dist/m-test-engine.json` `verbs` table (13 entries — includes
     `upgrade` and `watch`).
  3. `_cmd_capabilities` payload (11 entries — mirrors argparse).
  Sources 1 and 3 agree. Source 2 disagrees — it advertises verbs that
  don't exist in the CLI. (See Cross-cutting §6.)
- The `manifest` block in the output is a **flattened** subset of the
  on-disk manifest: omits `compose_file`, `repo_url`, `min_docker`,
  `run_args`, `verified_on`. Consumers that need those fields have to
  read the JSON file directly.
- `bind_mount.host` is the **expanded** path (`/home/rafael/m-work`,
  not `$HOME/m-work` as in the on-disk manifest). The expansion is one
  of the few places the manifest is preprocessed before exposure.
- No way to render this as text. Unlike `status` and `version`,
  capabilities is JSON-or-nothing.

---

## Cross-cutting observations

### 1. Verb inventory diverges across three sources

| Verb           | argparse wired? | `m engine capabilities` advertises? | `dist/m-test-engine.json` manifest? |
| -------------- | :-: | :-: | :-: |
| `status`       | ✓ | ✓ | ✓ |
| `install`      | ✓ | ✓ | ✓ |
| `start`        | ✓ | ✓ | ✓ |
| `stop`         | ✓ | ✓ | ✓ |
| `restart`      | ✓ | ✓ | ✓ |
| `logs`         | ✓ | ✓ | ✓ |
| `shell`        | ✓ | ✓ | ✓ |
| `exec`         | ✓ | ✓ | ✓ |
| `version`      | ✓ | ✓ | ✓ |
| `reset`        | ✓ | ✓ | ✓ |
| `capabilities` | ✓ | ✓ | ✓ |
| **`upgrade`**  | ✗ | ✗ | **✓** |
| **`watch`**    | ✗ | ✗ | **✓** |

`dist/m-test-engine.json` is the "vendored contract" that drives every
other piece of engine configuration — but its `verbs` table advertises
two actions (`upgrade`, `watch`) that no consumer can invoke. Either the
verbs are planned (the existence of `_classify_mismatches`'s
"image_outdated" code path hints at an upgrade flow) or the manifest is
stale; the CLI does not surface the gap.

### 2. `--help` shape is wildly inconsistent across verbs

| Verb           | `--help` lines | Description paragraph? | Inline example? | Documents exit semantics? |
| -------------- | :-: | :-: | :-: | :-: |
| `status`       | 5 | no  | no  | no (silent exit-1 path) |
| `install`      | 4 | no  | no  | no  |
| `start`        | 4 | no  | no  | no  |
| `stop`         | 4 | no  | no  | no  |
| `restart`      | 4 | no  | no  | no  |
| `logs`         | 5 | no  | no  | no  |
| `shell`        | 4 | no  | no  | no  |
| `exec`         | 7 | no  | **yes** (`'write $ZVERSION,!'`) | no  |
| `version`      | 5 | no  | no  | no  |
| `reset`        | 9 | **yes** | no  | no (refusal exits 2; not documented) |
| `capabilities` | 4 | no  | no  | no  |

Five verbs share the identical 4-line "two-line description-less" shape;
one verb has an embedded example; one has a description paragraph;
status/logs/version add a single flag and otherwise match. **None**
document exit-code semantics, even where they matter (`status`).

### 3. "Where the output comes from" is unpredictable

| Verb     | Success path source | Failure path source |
| -------- | ------------------- | ------------------- |
| `status` | m-cli synthesis     | m-cli synthesis     |
| `install`| `docker pull` raw   | `docker pull` raw   |
| `start` (already running) | m-cli synthesis | n/a       |
| `start` (from exited)     | `docker start` raw (container name) | `docker start` raw |
| `stop` (running)          | `docker stop` raw (container name)  | `docker stop` raw  |
| `stop` (no-op)            | (silent)            | n/a                 |
| `restart`                 | m-cli synthesis (`restarted X`) | propagated stderr |
| `logs`   | `docker logs` raw   | `docker logs` raw   |
| `shell`  | interactive TTY     | interactive TTY     |
| `exec`   | YDB raw stdout      | YDB raw `Error occurred:` |
| `version`| m-cli synthesis (table) | m-cli synthesis (`⚠`) |
| `reset` (no confirm) | m-cli synthesis (`refusing:`) | n/a |
| `reset --confirm`    | docker raw (chained) | docker raw (chained) |
| `capabilities` | m-cli synthesis (JSON) | n/a            |

Five categories of output sources mixed across 11 verbs. A user pasting
through the verbs for the first time sees:
- two custom m-cli tables (status / version),
- two single-line m-cli confirmations (start-running, restart),
- one m-cli refusal (reset),
- one JSON dump (capabilities),
- four passthrough flavours (docker echo, docker progress, docker logs,
  YDB output),
- two silent paths (stop-noop, logs-empty).

### 4. Glyph vocabulary inside the namespace

| Glyph   | Meaning            | Verbs that use it     |
| ------- | ------------------ | --------------------- |
| `✓`     | true / match       | `status`, `version`   |
| `✗`     | false / mismatch   | `status`, `version`   |
| `-`     | None (3 meanings)  | `status` (no healthcheck OR healthcheck-starting) |
| `—` (em-dash) | absent image label | `version` (no-label path; not exercised) |
| `(none)` literal | absent manifest counterpart | `version` (`image-rev` row) |
| `⚠`     | mismatch warning   | `status` (skew block), `version` (any-mismatch tail) |

Three distinct "value is missing" idioms — `-`, `—`, `(none)` — in
two adjacent verbs. The `-` glyph specifically conflates two semantically
different states ("starting" and "no healthcheck declared").

### 5. Exit-code conventions inside the namespace

| Exit | Used by                                                  |
| ---- | -------------------------------------------------------- |
| 0    | success (any verb), idempotent no-op (stop / start)      |
| 1    | `status` when container not running (text and JSON)      |
| 2    | argparse bad invocation; `reset` without `--confirm`     |
| 186  | YDB `%YDB-E-INVCMD` from `exec` (raw passthrough)        |
| other| any `docker pull` / `docker run` / `docker stop` failure (raw passthrough) |

`status`'s exit code is the only "useful" non-success exit any verb
produces from a successful invocation. It's also the only one not
documented in `--help`.

### 6. Manifest contract has drift detection in m-cli but not vice versa

`_classify_mismatches` (`engine_driver.py:265-308`) carefully diffs the
**image labels** against the manifest and flags `protocol_mismatch`,
`bind_mount_drift`, `ydb_version_drift`, `image_outdated`. But there is
no lint or check that diffs **`dist/m-test-engine.json`'s `verbs` table**
against `engine_cli.py`'s argparse registry. The verb-set drift
(§1 above) flows unchecked.

### 7. Sub-action verbs share zero rendering helpers

Each verb implements its own print loop. `status` uses a marks dict and
hand-formatted strings; `version` uses fixed-width formatting and dashes;
`capabilities` uses `json.dumps`; `restart` uses a single `print`. There
is no shared "engine output style" helper, despite the namespace having
the most consistent **need** for one (11 verbs, all sharing one
container, one image, one manifest).

### 8. `m doctor` and `m engine status` overlap but disagree on style

Both verbs report the engine's docker / image / container / health
state. `m doctor` (default-text) renders one row per check with `OK / WARN /
FAIL` and a tally line; `m engine status` renders a key-value tree with
✓/✗/- glyphs and no tally. The data is the same; the UX is two different
worlds, and neither references the other.

---

## Appendix A — probe sequence and engine state transitions

The audit drove the engine through this sequence (captured top to
bottom):

| Step | Command                       | Pre-state  | Post-state | Exit | Notable |
| ---- | ----------------------------- | ---------- | ---------- | :--: | ------- |
| 1    | `m engine status`             | running    | running    | 0    |         |
| 2    | `m engine status --json`      | running    | running    | 0    | 13 OCI labels |
| 3    | `m engine version`            | running    | running    | 0    | all ✓   |
| 4    | `m engine version --json`     | running    | running    | 0    |         |
| 5    | `m engine capabilities`       | running    | running    | 0    | 11 verbs |
| 6    | `m engine logs`               | running    | running    | 0    | empty   |
| 7    | `m engine exec 'write $ZVERSION,!'` | running | running | 0   | `GT.M V7.1-002…` |
| 8    | `m engine exec 'this is not M'` | running  | running    | 186  | YDB error |
| 9    | `m engine exec 'set x=1 write x,!'` | running | running | 0    |         |
| 10   | `m engine reset` (no `--confirm`) | running | running   | 2    | refusal |
| 11   | `m engine install`            | running    | running    | 0    | re-pull |
| 12   | `m engine start`              | running    | running    | 0    | "already running" |
| 13   | `m engine restart`            | running    | running    | 0    | "restarted m-test-engine" |
| 14   | `m engine status` (post-restart) | running | running    | 0    | `healthy: -` |
| 15   | `m engine stop`               | running    | stopped    | 0    | echoes container name |
| 16   | `m engine status` (stopped)   | stopped    | stopped    | **1**| `container up: ✗` |
| 17   | `m engine status --json`      | stopped    | stopped    | **1**| `container_running: false` |
| 18   | `m engine stop` (idempotent)  | stopped    | stopped    | 0    | silent  |
| 19   | `m engine start`              | stopped    | running    | 0    | echoes container name |
| 20   | `m engine status` (settled)   | running    | running    | 0    | all ✓   |

Engine ended where it started: container `m-test-engine` running and
healthy. `m engine reset --confirm` was not exercised (would wipe the
globals volume).

## Appendix B — files referenced

- `src/m_cli/engine_cli.py` — argparse wiring, verb dispatch, custom
  `_cmd_status` / `_cmd_capabilities` renderers.
- `src/m_cli/engine_driver.py` — `EngineDriver` protocol, `DockerDriver`
  implementation, `_classify_mismatches`, `_container_state`,
  `_container_health`.
- `src/m_cli/engine_manifest.py` — manifest loader (`load_engine_manifest`).
- `src/m_cli/_overview.py` — gh-style `print_overview` helper used by
  bare `m engine`.
- `dist/m-test-engine.json` — the vendored manifest contract (driver,
  image, container, bind-mount, run_args, verbs table, `verified_on`).
