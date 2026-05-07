# `m-env` Implementation Plan

**Document type:** self-contained implementation guide
**Target project:** separate proof-of-concept project, tentatively `m-env`
**Purpose:** prove containerized M execution-environment creation and management before folding the feature into `m-cli`
**Related local projects:**

- `~/projects/m-cli` — source-level M tooling; future integration target
- `~/projects/m-stdlib` — working YottaDB Dev Container reference; copy and adapt its `.devcontainer`, `Makefile`, `.gitignore`, and `tools/init-db.sh`

---

## 1. Executive Summary

`m-env` should prove one thing well: from a normal host checkout of an M project, create and manage a reproducible containerized execution environment for the two main M engines:

- **YottaDB**
- **InterSystems IRIS Community Edition**

The host filesystem remains the source of truth. Source files are edited on the host and mounted into the container at `/workspace`. Engine state, compiled artifacts, and runtime-specific files are either kept in gitignored project-local directories or Docker volumes.

The project should use adopted mainstream tooling:

- **Dev Containers** for development-environment metadata.
- **Dockerfiles** for building engine-specific development images.
- **Docker Compose** where the engine needs a long-running service, ports, durable storage, or multiple services.
- **Dev Container CLI** for lifecycle operations such as `up`, `exec`, and `down`.

`m-env` should not implement a custom orchestrator. It should generate standard files and delegate execution to standard tools.

---

## 2. Why Build This Outside `m-cli` First?

The current `m-cli` codebase is already mature around parser, formatter, linter, test runner, coverage, and LSP. Environment management is different: it touches Docker, host OS paths, user permissions, engine images, ports, volumes, passwords, and editor behavior.

Safer sequence:

1. Build `m-env` as a small proof-of-concept.
2. Prove generated YottaDB and IRIS environments work from scratch.
3. Reuse the generated templates and smoke tests when moving into `m-cli`.

The POC should be designed as a future `m-cli` module, but it should not start inside `m-cli`.

---

## 3. Initial User Experience

For an existing project:

```bash
m-env init --engine yottadb
m-env env up
m-env doctor
m-env env exec -- m test
```

For IRIS:

```bash
m-env init --engine iris
m-env env up --engine iris
m-env doctor --engine iris
m-env env terminal --engine iris
m-env env portal --engine iris
```

For a dual-engine project:

```bash
m-env init --engines yottadb,iris
m-env env up --engine yottadb
m-env doctor --engine yottadb
m-env env up --engine iris
m-env doctor --engine iris
```

Future `m-cli` shape:

```bash
m init --engine yottadb --devcontainer
m env up
m doctor
```

---

## 4. Proposed Project Layout

```text
m-env/
  README.md
  pyproject.toml
  src/
    m_env/
      __init__.py
      cli.py
      config.py
      doctor.py
      devcontainer.py
      filesystem.py
      render.py
      engines/
        __init__.py
        yottadb.py
        iris.py
      templates/
        common/
          gitignore.block
          vscode-settings.json
        yottadb/
          devcontainer.json.j2
          Dockerfile.j2
          init-db.sh.j2
          Makefile.fragment
        iris/
          devcontainer.json.j2
          docker-compose.yml.j2
          Dockerfile.j2
          post-create.sh.j2
  examples/
    hello-yottadb/
      src/
      tests/
    hello-iris/
      src/
      tests/
  tests/
    test_render_yottadb.py
    test_render_iris.py
    test_merge_gitignore.py
    test_config.py
  scripts/
    smoke-yottadb.sh
    smoke-iris.sh
```

Implementation language can be Python, matching `m-cli`, but the POC should stay small. Use simple file rendering and subprocess wrappers.

---

## 5. External Tools and Assumptions

### 5.1 Required Host Tools

`m-env doctor` should check:

```bash
docker --version
docker compose version
devcontainer --version
git --version
```

The Dev Container CLI is the reference implementation for reading `devcontainer.json`, creating containers, executing commands, and applying lifecycle commands.

Expected delegated operations:

```bash
devcontainer up --workspace-folder . --config .devcontainer/yottadb/devcontainer.json
devcontainer exec --workspace-folder . --config .devcontainer/yottadb/devcontainer.json m --version
devcontainer down --workspace-folder . --config .devcontainer/yottadb/devcontainer.json
```

### 5.2 Container-Internal Tooling

Every generated environment should install `m-cli` by cloning from GitHub:

```text
https://github.com/rafael5/m-cli
```

Do not use PyPI for `m-cli`. Inside the container, installation uses a venv and `uv pip install`.

Canonical install block:

```dockerfile
ARG M_CLI_REF=main

RUN git clone https://github.com/rafael5/m-cli /opt/m-cli && \
    cd /opt/m-cli && \
    git checkout "$M_CLI_REF" && \
    python3 -m venv .venv && \
    .venv/bin/python -m pip install --upgrade pip uv && \
    .venv/bin/uv pip install -e ".[lsp]" && \
    .venv/bin/uv pip install tree-sitter-m
```

All generated configs should point at:

```text
/opt/m-cli/.venv/bin/m
```

---

## 6. Configuration Model

`m-env` should generate and read an environment section in `.m-cli.toml`. This keeps the POC aligned with future `m-cli` integration.

Example:

```toml
[environment]
default = "yottadb"
workspace = "/workspace"

[environment.m_cli]
source = "git"
repo = "https://github.com/rafael5/m-cli"
ref = "main"
venv = "/opt/m-cli/.venv"
install = "uv"

[environment.yottadb]
type = "devcontainer"
image = "yottadb/yottadb-base:latest-master"
project_slug = "hello-yottadb"
source_dirs = ["src"]
test_dirs = ["tests"]
object_dir = ".objects"
database_dir = ".ydb"
global_directory = ".ydb/hello-yottadb.gld"
database_file = ".ydb/hello-yottadb.dat"
key_size = 1019
block_size = 4096

[environment.iris]
type = "devcontainer-compose"
image = "intersystems/iris-community:latest-cd"
project_slug = "hello-iris"
instance = "IRIS"
namespace = "USER"
durable_volume = "iris-durable"
durable_directory = "/durable/iris"
superserver_port = "1972:1972"
web_port = "52773:52773"
```

Command-line flags override config. Generated file rendering should be deterministic.

---

## 7. Command Design

### 7.1 `m-env init`

```bash
m-env init
m-env init --engine yottadb
m-env init --engine iris
m-env init --engines yottadb,iris
m-env init --engine yottadb --force
```

Responsibilities:

- Detect project root.
- Infer project slug from directory name.
- Detect `src/` and `tests/`, or create them if `--create-dirs`.
- Create/merge `.m-cli.toml`.
- Create/merge `.gitignore`.
- Generate `.devcontainer/<engine>/...`.
- Add optional Makefile fragments.

Default should be non-destructive. Existing generated files require `--force` to overwrite.

### 7.2 `m-env env`

```bash
m-env env up
m-env env up --engine yottadb
m-env env up --engine iris
m-env env exec -- m --version
m-env env exec -- m test
m-env env shell
m-env env down
m-env env rebuild
m-env env terminal --engine iris
m-env env portal --engine iris
```

Responsibilities:

- Locate selected engine config.
- Call Dev Container CLI.
- Pass through commands to `devcontainer exec`.
- For `portal`, print or open the IRIS Management Portal URL.
- For `terminal --engine iris`, run `iris session IRIS` in the container.

Avoid hidden Docker calls except for diagnostics. Lifecycle should go through `devcontainer`.

### 7.3 `m-env doctor`

```bash
m-env doctor
m-env doctor --engine yottadb
m-env doctor --engine iris
m-env doctor --all
m-env doctor --json
```

Responsibilities:

- Host checks.
- File checks.
- Engine config checks.
- Container checks when a container is running.
- Actionable repair suggestions.

Output should be human-readable by default and machine-readable with `--json`.

---

## 8. File Merge Rules

### 8.1 `.gitignore`

Append missing entries; preserve user content.

Recommended common block:

```gitignore
# YottaDB runtime artifacts
.ydb/
.objects/
*.o

# IRIS local secrets / optional host artifacts
.devcontainer/iris/password.txt
iris-password.txt

# Test + coverage outputs
test-results.tap
coverage.lcov
coverage.json
coverage.xml
htmlcov/

# Editor / OS
.vscode/
!.vscode/extensions.json
.idea/
.DS_Store
*.swp
*~

# Python (m-cli venv if cloned alongside)
.venv/
__pycache__/
*.pyc
```

Use marked blocks:

```gitignore
# m-env: begin
...
# m-env: end
```

If lines already exist elsewhere, do not duplicate them.

### 8.2 `.m-cli.toml`

Merge environment sections. Preserve existing lint/format configuration.

### 8.3 `.devcontainer`

Generate engine profiles in subdirectories:

```text
.devcontainer/yottadb/devcontainer.json
.devcontainer/iris/devcontainer.json
```

This avoids conflict with a project that already has `.devcontainer/devcontainer.json`.

---

## 9. YottaDB Implementation

### 9.1 Background

YottaDB provides an M runtime and database engine. Official documentation includes a Docker container and notes that database/routine data should be persisted by mounting storage when needed. The working local reference for this project is:

```text
~/projects/m-stdlib/.devcontainer/devcontainer.json
~/projects/m-stdlib/.devcontainer/Dockerfile
~/projects/m-stdlib/Makefile
~/projects/m-stdlib/tools/init-db.sh
~/projects/m-stdlib/.gitignore
```

Copy the practical pattern from `m-stdlib` and parameterize project names and directories.

### 9.2 Default YottaDB Shape

Use a single Dev Container, no Docker Compose:

```text
.devcontainer/yottadb/
  devcontainer.json
  Dockerfile
  scripts/
    init-db.sh
```

Why no Compose by default:

- YottaDB does not need a web portal.
- The common dev loop is command execution inside the container.
- Runtime behavior is mostly controlled through environment variables.
- A single container is simpler and closer to the working `m-stdlib` setup.

### 9.3 YottaDB Dev Container Template

```jsonc
{
  "name": "${project_slug} YottaDB dev",
  "build": {
    "dockerfile": "Dockerfile",
    "args": {
      "M_CLI_REF": "${m_cli_ref}"
    }
  },
  "remoteUser": "yottadb",
  "mounts": [
    "source=${localWorkspaceFolder},target=/workspace,type=bind,consistency=cached"
  ],
  "containerEnv": {
    "ydb_dist": "/opt/yottadb/current",
    "ydb_dir": "/workspace/.ydb",
    "ydb_gbldir": "/workspace/.ydb/${project_slug}.gld",
    "ydb_routines": "/workspace/src /workspace/tests /workspace/.objects /opt/yottadb/current",
    "PATH": "/opt/m-cli/.venv/bin:/opt/yottadb/current:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
  },
  "customizations": {
    "vscode": {
      "extensions": [
        "rafael5.tree-sitter-m-vscode",
        "github.vscode-github-actions",
        "redhat.vscode-yaml",
        "ms-azuretools.vscode-docker",
        "eamodio.gitlens"
      ],
      "settings": {
        "m-cli.enabled": true,
        "m-cli.path": "/opt/m-cli/.venv/bin/m",
        "editor.formatOnSave": true,
        "[m]": {
          "editor.tabSize": 1,
          "editor.insertSpaces": true,
          "editor.detectIndentation": false
        }
      }
    }
  },
  "postCreateCommand": "make setup-ydb && /opt/m-cli/.venv/bin/m --version",
  "forwardPorts": []
}
```

### 9.4 YottaDB Dockerfile Template

```dockerfile
FROM yottadb/yottadb-base:latest-master

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip git build-essential \
        libssl-dev libcurl4-openssl-dev libsodium-dev zlib1g-dev libpcre2-dev \
        bash make ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG M_CLI_REF=main

RUN git clone https://github.com/rafael5/m-cli /opt/m-cli && \
    cd /opt/m-cli && \
    git checkout "$M_CLI_REF" && \
    python3 -m venv .venv && \
    .venv/bin/python -m pip install --upgrade pip uv && \
    .venv/bin/uv pip install -e ".[lsp]" && \
    .venv/bin/uv pip install tree-sitter-m

USER yottadb
WORKDIR /workspace

RUN echo '. /opt/yottadb/current/ydb_env_set' >> /home/yottadb/.bashrc && \
    echo 'export PATH="/opt/m-cli/.venv/bin:$PATH"' >> /home/yottadb/.bashrc
```

### 9.5 YottaDB Configuration Parameters

| Parameter | Generated Value | Purpose |
|---|---|---|
| `ydb_dist` | `/opt/yottadb/current` | YottaDB installation inside the container. |
| `ydb_dir` | `/workspace/.ydb` | Project-local database directory. |
| `ydb_gbldir` | `/workspace/.ydb/${project_slug}.gld` | Project global directory. |
| `ydb_routines` | `/workspace/src /workspace/tests /workspace/.objects /opt/yottadb/current` | Source, tests, compiled object directory, and runtime routines. |
| `.objects` | `/workspace/.objects` | Object-code output; gitignored. |
| `.ydb` | `/workspace/.ydb` | Database and global directory; gitignored. |
| `KEY_SIZE` | `1019` | Prevents YDB trace subscript overflow during coverage on deep trace paths. |
| `BLOCK_SIZE` | `4096` | Works with the larger key size. |

The `KEY_SIZE=1019` and `BLOCK_SIZE=4096` values come from the `m-stdlib` investigation. YDB coverage trace keys can become deeply nested under `FOR_LOOP` / `*CHILDREN`; the default key size can raise `%YDB-E-GVSUBOFLOW`.

### 9.6 YottaDB `init-db.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_SLUG="${PROJECT_SLUG:-hello-yottadb}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
YDB_DIR="$PROJECT_ROOT/.ydb"
GLD="$YDB_DIR/${PROJECT_SLUG}.gld"
DAT="$YDB_DIR/${PROJECT_SLUG}.dat"

if [[ -f "$GLD" && -f "$DAT" ]]; then
    exit 0
fi

YDB_DIST="${ydb_dist:-/opt/yottadb/current}"
mkdir -p "$YDB_DIR" "$PROJECT_ROOT/.objects"

export ydb_dist="$YDB_DIST"
export ydb_gbldir="$GLD"
unset ydb_routines

"$YDB_DIST/mumps" -run GDE <<EOF
change -segment DEFAULT -file_name="$DAT"
change -region DEFAULT -dynamic_segment=DEFAULT -KEY_SIZE=1019
change -segment DEFAULT -BLOCK_SIZE=4096
exit
EOF

"$YDB_DIST/mupip" create
```

### 9.7 YottaDB Makefile Fragment

```makefile
PROJECT ?= ${project_slug}
YDB_DIST ?= /opt/yottadb/current
M ?= /opt/m-cli/.venv/bin/m

YDB_ENV := unset gtmdir gtm_dist gtmgbldir gtmroutines ; \
           export ydb_dist="$(YDB_DIST)" \
                  ydb_dir="$(CURDIR)/.ydb" \
                  ydb_gbldir="$(CURDIR)/.ydb/$(PROJECT).gld" \
                  ydb_routines="$(CURDIR)/src $(CURDIR)/tests $(CURDIR)/.objects $(YDB_DIST)" \
                  PATH="/opt/m-cli/.venv/bin:$(YDB_DIST):$$PATH"

.PHONY: setup-ydb test coverage check

setup-ydb:
	@mkdir -p .objects
	@PROJECT_SLUG="$(PROJECT)" bash .devcontainer/yottadb/scripts/init-db.sh

test: setup-ydb
	@$(YDB_ENV) && $(M) test tests/

coverage: setup-ydb
	@$(YDB_ENV) && $(M) coverage --routines src --tests tests --format=lcov > coverage.lcov

check:
	@$(M) fmt --check src/ tests/
	@$(M) lint --error-on=error src/ tests/
	@$(MAKE) test
```

### 9.8 YottaDB Smoke Test

```bash
set -euo pipefail

PROJECT=examples/hello-yottadb

m-env init --engine yottadb "$PROJECT"
devcontainer up --workspace-folder "$PROJECT" --config "$PROJECT/.devcontainer/yottadb/devcontainer.json"
devcontainer exec --workspace-folder "$PROJECT" --config "$PROJECT/.devcontainer/yottadb/devcontainer.json" m --version
devcontainer exec --workspace-folder "$PROJECT" --config "$PROJECT/.devcontainer/yottadb/devcontainer.json" make setup-ydb
devcontainer exec --workspace-folder "$PROJECT" --config "$PROJECT/.devcontainer/yottadb/devcontainer.json" make check
```

### 9.9 YottaDB Doctor Checks

Host:

- Docker installed.
- Dev Container CLI installed.
- `.devcontainer/yottadb/devcontainer.json` exists.
- `.devcontainer/yottadb/Dockerfile` exists.
- `.devcontainer/yottadb/scripts/init-db.sh` exists.

Container:

- `/opt/yottadb/current` exists.
- `/opt/yottadb/current/mumps` executable.
- `/opt/yottadb/current/mupip` executable.
- `/opt/m-cli/.venv/bin/m --version` works.
- `/workspace` mounted.
- `.ydb` and `.objects` can be created.
- Global directory exists after `make setup-ydb`.
- `ydb_routines` includes source, tests, `.objects`, and runtime.

---

## 10. InterSystems IRIS Community Implementation

### 10.1 Background

InterSystems publishes IRIS Community Edition images. The common public image is:

```text
intersystems/iris-community:latest-cd
```

IRIS exposes two important ports:

- `1972` — SuperServer / client connections
- `52773` — web server / Management Portal

IRIS containers support durable storage through:

```text
ISC_DATA_DIRECTORY=/durable/iris
```

The interactive terminal is:

```bash
iris session IRIS
```

IRIS Community Edition may require CPU limiting on high-core machines. Generated Compose should include commented guidance for `cpuset` and `cpus`.

### 10.2 Default IRIS Shape

Use Dev Container + Docker Compose:

```text
.devcontainer/iris/
  devcontainer.json
  docker-compose.yml
  Dockerfile
  scripts/
    post-create.sh
```

Why Compose:

- IRIS is a long-running service.
- Ports are part of normal development.
- The Management Portal is a first-class workflow.
- Durable storage is important.
- Password initialization is a container lifecycle concern.

### 10.3 IRIS Dev Container Template

```jsonc
{
  "name": "${project_slug} IRIS dev",
  "dockerComposeFile": "docker-compose.yml",
  "service": "iris",
  "workspaceFolder": "/workspace",
  "remoteUser": "irisowner",
  "customizations": {
    "vscode": {
      "extensions": [
        "rafael5.tree-sitter-m-vscode",
        "github.vscode-github-actions",
        "redhat.vscode-yaml",
        "ms-azuretools.vscode-docker",
        "eamodio.gitlens"
      ],
      "settings": {
        "m-cli.enabled": true,
        "m-cli.path": "/opt/m-cli/.venv/bin/m",
        "editor.formatOnSave": true,
        "[m]": {
          "editor.tabSize": 1,
          "editor.insertSpaces": true,
          "editor.detectIndentation": false
        }
      }
    }
  },
  "forwardPorts": [1972, 52773],
  "portsAttributes": {
    "1972": {
      "label": "IRIS SuperServer"
    },
    "52773": {
      "label": "IRIS Management Portal",
      "onAutoForward": "notify"
    }
  },
  "postCreateCommand": ".devcontainer/iris/scripts/post-create.sh"
}
```

### 10.4 IRIS Docker Compose Template

```yaml
services:
  iris:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        M_CLI_REF: ${M_CLI_REF:-main}
    init: true
    container_name: ${COMPOSE_PROJECT_NAME:-m-project}-iris
    volumes:
      - ../..:/workspace:cached
      - iris-durable:/durable
    environment:
      ISC_DATA_DIRECTORY: /durable/iris
    ports:
      - "1972:1972"
      - "52773:52773"
    # InterSystems IRIS Community Edition has CPU limits. Uncomment on
    # high-core hosts if the container refuses to start.
    # cpuset: "0-19"
    # cpus: "20"

volumes:
  iris-durable:
```

### 10.5 IRIS Dockerfile Template

```dockerfile
FROM intersystems/iris-community:latest-cd

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip git build-essential \
        bash make ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG M_CLI_REF=main

RUN git clone https://github.com/rafael5/m-cli /opt/m-cli && \
    cd /opt/m-cli && \
    git checkout "$M_CLI_REF" && \
    python3 -m venv .venv && \
    .venv/bin/python -m pip install --upgrade pip uv && \
    .venv/bin/uv pip install -e ".[lsp]" && \
    .venv/bin/uv pip install tree-sitter-m

WORKDIR /workspace

USER irisowner
```

### 10.6 IRIS Post-Create Script

```bash
#!/usr/bin/env bash
set -euo pipefail

/opt/m-cli/.venv/bin/m --version

echo "IRIS Community container is ready."
echo "Management Portal: http://localhost:52773/csp/sys/UtilHome.csp"
echo "Terminal: iris session IRIS"
```

### 10.7 IRIS Password Strategy

Do not commit passwords.

Default POC mode:

- Do not generate a password file.
- Let IRIS Community Edition use its documented first-login behavior.
- Print the Management Portal URL and reminder.

Optional password-file mode:

```bash
m-env init --engine iris --password-file .devcontainer/iris/password.txt
```

Generated Compose addition:

```yaml
    volumes:
      - ../..:/workspace:cached
      - iris-durable:/durable
      - ./password.txt:/durable/password/password.txt:ro
    command: --password-file /durable/password/password.txt
```

Always gitignore:

```gitignore
.devcontainer/iris/password.txt
```

### 10.8 IRIS Smoke Test

```bash
set -euo pipefail

PROJECT=examples/hello-iris

m-env init --engine iris "$PROJECT"
devcontainer up --workspace-folder "$PROJECT" --config "$PROJECT/.devcontainer/iris/devcontainer.json"
devcontainer exec --workspace-folder "$PROJECT" --config "$PROJECT/.devcontainer/iris/devcontainer.json" /opt/m-cli/.venv/bin/m --version
devcontainer exec --workspace-folder "$PROJECT" --config "$PROJECT/.devcontainer/iris/devcontainer.json" iris session IRIS < /dev/null || true
```

The last line may need adjustment because interactive IRIS terminal behavior is TTY-sensitive. If noninteractive use is required, create an IRIS script or command wrapper in a later iteration.

### 10.9 IRIS Doctor Checks

Host:

- Docker installed.
- Docker Compose installed.
- Dev Container CLI installed.
- `.devcontainer/iris/devcontainer.json` exists.
- `.devcontainer/iris/docker-compose.yml` exists.
- `.devcontainer/iris/Dockerfile` exists.

Container:

- IRIS service is running.
- `/workspace` is mounted.
- `/durable` is mounted.
- `ISC_DATA_DIRECTORY` is set.
- `/opt/m-cli/.venv/bin/m --version` works.
- `iris session IRIS` is available.
- Ports are mapped or intentionally disabled:
  - `1972`
  - `52773`
- Management Portal URL is printed:
  - `http://localhost:52773/csp/sys/UtilHome.csp`

Error-specific guidance:

- If IRIS exits on a high-core host, suggest uncommenting:

```yaml
cpuset: "0-19"
cpus: "20"
```

---

## 11. Integrated Engine Comparison

| Concern | YottaDB | IRIS Community |
|---|---|---|
| Default mode | Single Dev Container | Dev Container + Docker Compose |
| Image | `yottadb/yottadb-base:latest-master` | `intersystems/iris-community:latest-cd` |
| Runtime user | `yottadb` | `irisowner` |
| Workspace | `/workspace` bind mount | `/workspace` bind mount |
| Persistent state | Project-local `.ydb/` | Docker volume `iris-durable` at `/durable` |
| Compiled artifacts | `.objects/` | Engine-managed for now |
| Main config | `ydb_dist`, `ydb_dir`, `ydb_gbldir`, `ydb_routines` | `ISC_DATA_DIRECTORY`, instance, namespace |
| Init script | `init-db.sh` runs GDE + MUPIP | `post-create.sh` verifies runtime |
| Ports | none by default | `1972`, `52773` |
| UI | none | Management Portal |
| Terminal | shell + `mumps` / `mupip` | `iris session IRIS` |
| Current `m-cli` test support | yes | future adapter |
| Current `m-cli` coverage support | yes | future adapter |
| Special risk | trace subscript key overflow | CPU limit, password handling, durable storage permissions |
| Best first smoke | `make setup-ydb && make check` | container up + `m --version` + terminal availability |

---

## 12. Implementation Phases

### Phase 0 — Project Skeleton

Deliverables:

- Python CLI project.
- `m-env --help`.
- Basic config model.
- Template renderer.
- Merge helpers for `.gitignore` and `.m-cli.toml`.

Exit criteria:

```bash
m-env --help
pytest
```

### Phase 1 — YottaDB Generation

Deliverables:

- `m-env init --engine yottadb`.
- Generate YottaDB Dev Container files.
- Generate `init-db.sh`.
- Merge `.gitignore`.
- Optional Makefile fragment.

Exit criteria:

```bash
devcontainer up --workspace-folder examples/hello-yottadb --config examples/hello-yottadb/.devcontainer/yottadb/devcontainer.json
devcontainer exec --workspace-folder examples/hello-yottadb --config examples/hello-yottadb/.devcontainer/yottadb/devcontainer.json make check
```

### Phase 2 — YottaDB Doctor and Lifecycle

Deliverables:

- `m-env doctor --engine yottadb`.
- `m-env env up/down/exec/shell`.

Exit criteria:

```bash
m-env env up --engine yottadb
m-env doctor --engine yottadb
m-env env exec -- m test
```

### Phase 3 — IRIS Generation

Deliverables:

- `m-env init --engine iris`.
- Generate IRIS Dev Container + Compose files.
- Generate Dockerfile and post-create script.
- Merge `.gitignore`.

Exit criteria:

```bash
devcontainer up --workspace-folder examples/hello-iris --config examples/hello-iris/.devcontainer/iris/devcontainer.json
devcontainer exec --workspace-folder examples/hello-iris --config examples/hello-iris/.devcontainer/iris/devcontainer.json /opt/m-cli/.venv/bin/m --version
```

### Phase 4 — IRIS Doctor and Helpers

Deliverables:

- `m-env doctor --engine iris`.
- `m-env env terminal --engine iris`.
- `m-env env portal --engine iris`.
- CPU-limit detection guidance.

Exit criteria:

```bash
m-env env up --engine iris
m-env doctor --engine iris
m-env env portal --engine iris
```

### Phase 5 — Dual-Engine Projects

Deliverables:

- `m-env init --engines yottadb,iris`.
- `m-env doctor --all`.
- Engine-selection rules.

Exit criteria:

```bash
m-env init --engines yottadb,iris examples/dual
m-env doctor --all
```

### Phase 6 — Prepare for `m-cli` Integration

Deliverables:

- Stable templates.
- Smoke scripts.
- README section mapping `m-env` commands to future `m` commands.
- Integration notes for `~/projects/m-cli`.

Future target module in `m-cli`:

```text
src/m_cli/environment/
  cli.py
  config.py
  doctor.py
  devcontainer.py
  engines/
    yottadb.py
    iris.py
  templates/
```

---

## 13. Test Strategy

### 13.1 Unit Tests

Test without Docker:

- Template rendering.
- Project slug normalization.
- `.gitignore` merge.
- `.m-cli.toml` merge.
- Engine selection.
- Command construction for `devcontainer`.
- Refusal to overwrite without `--force`.

### 13.2 Snapshot Tests

Use golden files for generated:

- YottaDB `devcontainer.json`
- YottaDB `Dockerfile`
- YottaDB `init-db.sh`
- IRIS `devcontainer.json`
- IRIS `docker-compose.yml`
- IRIS `Dockerfile`
- IRIS `post-create.sh`

### 13.3 Smoke Tests

Run manually or in an opt-in CI job:

```bash
scripts/smoke-yottadb.sh
scripts/smoke-iris.sh
```

Keep these separate from normal unit tests because they pull large images and require Docker.

---

## 14. Known Risks

| Risk | Mitigation |
|---|---|
| Docker not installed or inaccessible | `m-env doctor` explains install/socket/permissions issue. |
| Dev Container CLI absent | Show install instructions and exact command. |
| IRIS image is large | Make IRIS smoke opt-in. |
| IRIS ports already used | Detect or allow port overrides. |
| IRIS Community CPU limit | Generate commented `cpuset` / `cpus` and doctor guidance. |
| Password leakage | Never generate committed password files; gitignore local password path. |
| YottaDB trace key overflow | Always generate `KEY_SIZE=1019`, `BLOCK_SIZE=4096`. |
| Existing project files overwritten | Require `--force`; otherwise merge or fail with explanation. |
| Network failure during Docker build | Dockerfile clone is transparent; user can rerun build. |
| `m-cli` main changes unexpectedly | Support `--m-cli-ref <commit>` for reproducible builds. |

---

## 15. Definition of Done

The POC is successful when:

1. `m-env init --engine yottadb examples/hello-yottadb` generates a working YottaDB Dev Container.
2. `devcontainer up` starts the YottaDB container.
3. `make setup-ydb` creates `.ydb/*.gld` and `.ydb/*.dat`.
4. `m test` runs inside the YottaDB container.
5. `m-env init --engine iris examples/hello-iris` generates a working IRIS Dev Container.
6. `devcontainer up` starts the IRIS container.
7. `m --version` runs inside the IRIS container.
8. IRIS Management Portal is reachable on the forwarded port.
9. `m-env doctor` gives useful diagnostics for both engines.
10. The generated templates are ready to move into `~/projects/m-cli`.

---

## 16. Reference Links

- Dev Container overview and specification: <https://containers.dev/overview>
- Dev Container Dockerfile / Docker Compose guide: <https://containers.dev/guide/dockerfile>
- Dev Container CLI repository: <https://github.com/devcontainers/cli>
- YottaDB Docker container documentation: <https://docs.yottadb.com/AdminOpsGuide/containers.html>
- YottaDB documentation index: <https://docs.yottadb.net/>
- InterSystems IRIS Community Docker Hub image: <https://hub.docker.com/r/intersystems/iris-community>
- InterSystems IRIS Community with Docker guide: <https://developer.intersystems.com/next-steps/get-intersystems-iris-community-with-docker/>
- InterSystems Container Registry documentation: <https://docs.intersystems.com/components/csp/docbook/DocBook.UI.Page.cls?KEY=PAGE_containerregistry>
- Local YottaDB working reference: `~/projects/m-stdlib`
- Future integration target: `~/projects/m-cli`
