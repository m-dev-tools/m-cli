# `m environment` / `m doctor` / `m init` — Engine Environment Strategy

**Document type:** design proposal
**Scope:** Commands for creating, configuring, diagnosing, and managing containerized M execution environments for YottaDB and InterSystems IRIS Community Edition.
**Principle:** use mainstream container development standards — Dev Containers, Dockerfiles, Docker Compose where appropriate, and the Dev Container CLI — rather than inventing an `m-cli` container orchestrator.

---

## 1. Goal

`m-cli` should make the M execution environment as approachable as the language tooling itself. A newcomer should be able to clone or create an M project, run one command, and get a working runtime container with the host source tree mounted into it.

Target experience:

```bash
m init --engine yottadb --devcontainer
m env up
m doctor
m check
```

or, for IRIS:

```bash
m init --engine iris --devcontainer
m env up --engine iris
m doctor --engine iris
m env portal
```

The active source tree stays on the host filesystem. The engine runs inside a container. Editors and CI consume the same `.devcontainer` files.

---

## 2. Command Surface

### 2.1 `m init`

Initialize an M project for local development.

```bash
m init
m init --engine yottadb
m init --engine iris
m init --engine yottadb --devcontainer
m init --engine iris --devcontainer
m init --engines yottadb,iris --devcontainer
```

Responsibilities:

- Create or update `.m-cli.toml`.
- Detect or create conventional source/test directories.
- Configure the default engine.
- Optionally generate Dev Container assets.
- Optionally add `.gitignore` entries for engine artifacts.
- Optionally add Makefile targets or scripts for engine setup.

`m init` is the brownfield adoption command. It should be safe to run in an existing repository and should preserve user files.

### 2.2 `m environment create`

Generate engine-specific container configuration.

```bash
m environment create yottadb
m environment create iris
m environment create --all
m environment create yottadb --m-cli-ref main
m environment create iris --m-cli-ref <commit-sha>
```

Alias:

```bash
m env create yottadb
```

Responsibilities:

- Generate `.devcontainer/<engine>/devcontainer.json`.
- Generate engine-specific Dockerfile and helper scripts.
- Generate Docker Compose only when the engine or project shape benefits from it.
- Configure `m-cli` inside the container by cloning `https://github.com/rafael5/m-cli`.
- Install Python packages with `uv pip install`, not bare `pip`.

### 2.3 `m env`

Manage the generated environment by delegating to Dev Container tooling.

```bash
m env up
m env up --engine yottadb
m env up --engine iris
m env exec -- m test
m env shell
m env down
m env rebuild
m env portal
m env terminal
```

Implementation rule: `m env` should call standard tools, primarily:

```bash
devcontainer up --workspace-folder .
devcontainer exec --workspace-folder . <command>
devcontainer down --workspace-folder .
```

For multi-config repositories, pass the selected config path:

```bash
devcontainer up \
  --workspace-folder . \
  --config .devcontainer/yottadb/devcontainer.json
```

### 2.4 `m doctor`

Diagnose the host project and the active engine environment.

```bash
m doctor
m doctor --engine yottadb
m doctor --engine iris
m doctor --container
m doctor --json
```

Responsibilities:

- Check host prerequisites: Docker, Docker Compose, Dev Container CLI.
- Check generated files: `.devcontainer`, `.m-cli.toml`, `.gitignore`.
- Check engine-specific runtime state.
- Check `m-cli` inside the container.
- Emit actionable fixes.
- Exit nonzero when the environment cannot run tests.

---

## 3. Configuration Model

Environment behavior should be configuration-driven. `.m-cli.toml` is the project source of truth; generated Dev Container files are the execution substrate.

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
project_slug = "my-project"
source_dirs = ["src"]
test_dirs = ["tests"]
object_dir = ".objects"
database_dir = ".ydb"
global_directory = ".ydb/my-project.gld"
database_file = ".ydb/my-project.dat"
key_size = 1019
block_size = 4096

[environment.iris]
type = "devcontainer-compose"
image = "intersystems/iris-community:latest-cd"
instance = "IRIS"
namespace = "USER"
durable_volume = "iris-durable"
durable_directory = "/durable/iris"
superserver_port = "1972:1972"
web_port = "52773:52773"
```

Command-line flags override config values. Generated files should include comments saying they are managed by `m-cli` and can be regenerated.

---

## 4. Shared Container Strategy

### 4.1 Use Dev Containers

Dev Containers are the right standard layer because they are supported by VS Code, GitHub Codespaces, the Dev Container CLI, and other modern developer tools. The primary file is `devcontainer.json`, normally placed under `.devcontainer/`.

For multiple engine profiles, use one subdirectory per engine:

```text
.devcontainer/
  yottadb/
    devcontainer.json
    Dockerfile
    scripts/
      init-db.sh
  iris/
    devcontainer.json
    docker-compose.yml
    Dockerfile
    scripts/
      post-create.sh
```

### 4.2 Clone `m-cli` From GitHub

Do not rely on PyPI. Container images should clone `m-cli` from GitHub and install it into a venv with `uv pip install`.

Canonical install pattern:

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

All generated editor and PATH settings should point at:

```text
/opt/m-cli/.venv/bin/m
```

### 4.3 Keep Source on the Host

The project root should be bind-mounted into the container:

```jsonc
"mounts": [
  "source=${localWorkspaceFolder},target=/workspace,type=bind,consistency=cached"
]
```

For Docker Compose:

```yaml
volumes:
  - ../..:/workspace:cached
```

### 4.4 Preserve User Files

`m init` and `m environment create` must be merge-aware:

- Do not overwrite `.gitignore`; append missing entries.
- Do not overwrite `.m-cli.toml`; merge environment sections.
- Do not overwrite existing `.devcontainer` profiles without `--force`.
- Keep generated blocks marked.

---

## 5. YottaDB Environment

The YottaDB profile should be modeled on the working `m-stdlib` devcontainer pattern.

### 5.1 Default Shape

Default: single-container Dev Container, no Docker Compose.

Generated files:

```text
.devcontainer/yottadb/
  devcontainer.json
  Dockerfile
  scripts/
    init-db.sh
```

YottaDB does not need Compose for the common case because the runtime is driven by environment variables and source paths.

### 5.2 `devcontainer.json`

Template:

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

### 5.3 Dockerfile

Template:

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

### 5.4 Database Initialization

Generated `scripts/init-db.sh` should be idempotent.

Important YottaDB parameters:

| Parameter | Recommended Value | Why |
|---|---:|---|
| `ydb_dist` | `/opt/yottadb/current` | Container runtime location. |
| `ydb_dir` | `/workspace/.ydb` | Project-local database state. |
| `ydb_gbldir` | `/workspace/.ydb/${project_slug}.gld` | Project global directory. |
| `ydb_routines` | `/workspace/src /workspace/tests /workspace/.objects /opt/yottadb/current` | Source, tests, object output, runtime. |
| object dir | `.objects` | Keeps compiled artifacts out of source dirs. |
| database dir | `.ydb` | Keeps database artifacts project-local and gitignored. |
| `KEY_SIZE` | `1019` | Avoids YDB trace subscript overflow during coverage on deeply nested trace keys. |
| `BLOCK_SIZE` | `4096` | Required with large key size. |

Template:

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
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

### 5.5 Makefile Targets

`m environment create yottadb` should optionally add:

```makefile
setup-ydb:
	@mkdir -p .objects
	@bash .devcontainer/yottadb/scripts/init-db.sh
```

Project-level commands should run with a constructed YDB environment:

```makefile
YDB_ENV := unset gtmdir gtm_dist gtmgbldir gtmroutines ; \
           export ydb_dist="$(YDB_DIST)" \
                  ydb_dir="$(CURDIR)/.ydb" \
                  ydb_gbldir="$(CURDIR)/.ydb/$(PROJECT).gld" \
                  ydb_routines="$(CURDIR)/src $(CURDIR)/tests $(CURDIR)/.objects $(YDB_DIST)" \
                  PATH="$(YDB_DIST):$$PATH"
```

### 5.6 YottaDB Doctor Checks

`m doctor --engine yottadb` should verify:

- `ydb_dist` exists.
- `mumps` and `mupip` are executable.
- `.ydb` exists or can be created.
- `.objects` exists or can be created.
- `ydb_gbldir` points to an existing `.gld` after setup.
- `ydb_routines` includes source, tests, object dir, and runtime.
- `m test` can discover tests.
- `m coverage` can run without `%YDB-E-GVSUBOFLOW`.

---

## 6. InterSystems IRIS Community Environment

IRIS Community Edition should default to a Dev Container backed by Docker Compose.

### 6.1 Default Shape

Generated files:

```text
.devcontainer/iris/
  devcontainer.json
  docker-compose.yml
  Dockerfile
  scripts/
    post-create.sh
```

Compose is appropriate for IRIS because the container is a long-running service with a Management Portal, a SuperServer port, durable storage, and password/lifecycle concerns.

### 6.2 Image and Ports

Default image:

```text
intersystems/iris-community:latest-cd
```

Important ports:

| Port | Purpose |
|---:|---|
| `1972` | IRIS SuperServer / client connections |
| `52773` | Management Portal / web server |

The generated environment should forward both by default, while allowing host port overrides.

### 6.3 `devcontainer.json`

Template:

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

### 6.4 Docker Compose

Template:

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

### 6.5 Dockerfile

Template:

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

### 6.6 Post-Create Script

Template:

```bash
#!/usr/bin/env bash
set -euo pipefail

/opt/m-cli/.venv/bin/m --version

echo "IRIS Community container is ready."
echo "Management Portal: http://localhost:52773/csp/sys/UtilHome.csp"
echo "Terminal: iris session IRIS"
```

Later, when `m test` has an IRIS runner, this can become:

```bash
/opt/m-cli/.venv/bin/m doctor --engine iris
/opt/m-cli/.venv/bin/m test --engine iris tests/
```

### 6.7 Password Strategy

Do not commit real credentials.

Default beginner mode:

- Let IRIS use the Community Edition default first-login behavior.
- Document that `_SYSTEM` / `SYS` may require password change.

Optional local password-file mode:

```bash
m environment create iris --password-file .devcontainer/iris/password.txt
```

Generated Compose addition:

```yaml
    volumes:
      - ../..:/workspace:cached
      - iris-durable:/durable
      - ./password.txt:/durable/password/password.txt:ro
    command: --password-file /durable/password/password.txt
```

Generated `.gitignore` addition:

```gitignore
.devcontainer/iris/password.txt
```

### 6.8 IRIS Doctor Checks

`m doctor --engine iris` should verify:

- Docker/Dev Container/Compose are available.
- `iris` service is running.
- Ports `1972` and `52773` are exposed or intentionally disabled.
- Durable storage is configured.
- `iris session IRIS` works inside the container.
- `/opt/m-cli/.venv/bin/m --version` works.
- Source workspace is mounted at `/workspace`.
- Management Portal URL is reachable when ports are forwarded.
- CPU-limit guidance is shown if the container exits with a Community Edition core-limit error.

---

## 7. Integrated Engine Table

| Concern | YottaDB | IRIS Community |
|---|---|---|
| Default container mode | Single Dev Container | Dev Container + Docker Compose |
| Default image | `yottadb/yottadb-base:latest-master` | `intersystems/iris-community:latest-cd` |
| Main runtime user | `yottadb` | `irisowner` |
| Workspace mount | `/workspace` bind mount | `/workspace` bind mount |
| Persistent state | Project-local `.ydb/` | Docker volume `iris-durable` mounted at `/durable` |
| Object artifacts | Project-local `.objects/` | Engine-managed; future adapter may add project cache dirs |
| Runtime path config | `ydb_dist`, `ydb_dir`, `ydb_gbldir`, `ydb_routines` | `ISC_DATA_DIRECTORY`, instance name, namespace |
| Test execution today | Supported by `m test` YottaDB runner | Future runner adapter |
| Coverage today | Supported by `m coverage` via YDB `view "TRACE"` | Future coverage adapter |
| Web UI | None by default | Management Portal on `52773` |
| Main external port | None | `1972`, `52773` |
| Init script | `init-db.sh` creates `.gld` + `.dat` | `post-create.sh` verifies IRIS and `m-cli` |
| Special setup | `KEY_SIZE=1019`, `BLOCK_SIZE=4096` for trace safety | Durable `%SYS`, optional password file, possible CPU limit |
| Best generated command | `m environment create yottadb` | `m environment create iris` |
| Doctor focus | env vars, global directory, routines path, trace safety | service health, ports, durable storage, terminal, portal |

---

## 8. Common Strategy

The shared strategy is:

1. **Use Dev Containers as the contract.** `m-cli` generates standard files; editors, CI, and the Dev Container CLI run them.
2. **Use Dockerfiles for tool installation.** Both engines clone `m-cli` from GitHub and install it with `uv pip install` into `/opt/m-cli/.venv`.
3. **Use Compose only where it earns its keep.** YottaDB defaults to a simple single-container profile; IRIS defaults to Compose because ports, durable storage, and service lifecycle are first-class.
4. **Keep source on the host.** Runtime containers mount `/workspace`; generated artifacts are gitignored.
5. **Make `.m-cli.toml` the source of intent.** Dev Container files are generated from config and may be regenerated.
6. **Expose one lifecycle vocabulary.** `m env up`, `m env exec`, `m env shell`, `m env down`, `m doctor`.
7. **Keep engine differences behind adapters.** The command surface should be common even though YottaDB and IRIS have different runtime mechanics.

---

## 9. Proposed Implementation Order

1. Add `m doctor` host checks:
   - Docker
   - Docker Compose
   - Dev Container CLI
   - project config

2. Add `m init --engine yottadb --devcontainer`:
   - `.m-cli.toml`
   - `.devcontainer/yottadb/*`
   - `.gitignore` block
   - setup script

3. Add `m env up/exec/shell/down` for generated Dev Containers.

4. Add YottaDB container doctor:
   - verify `mumps`, `mupip`, `.gld`, `ydb_routines`
   - run `m test` smoke when tests exist

5. Add `m init --engine iris --devcontainer`:
   - `.devcontainer/iris/*`
   - Compose service
   - durable storage
   - portal/terminal helpers

6. Add IRIS container doctor:
   - verify service, ports, durable storage, terminal, portal

7. Add dual-engine support:
   - `.devcontainer/yottadb`
   - `.devcontainer/iris`
   - `m env up --engine ...`
   - `m doctor --all`

8. Later, when runtime adapters exist:
   - `m test --engine iris`
   - `m coverage --engine iris`
   - `m check --engine iris`
   - `m check --all-engines`

---

## 10. References

- Dev Container Specification: `devcontainer.json`, Dockerfile, and Docker Compose support.
- Dev Container CLI: `devcontainer up`, `devcontainer exec`, `devcontainer down`.
- YottaDB container documentation: public YottaDB Docker images and runtime environment conventions.
- InterSystems IRIS Community Docker Hub documentation: `intersystems/iris-community:latest-cd`, ports `1972` and `52773`, `iris session IRIS`, durable storage, password-file option, and Community Edition CPU-limit note.
- `m-stdlib` working YottaDB devcontainer: concrete local reference for the YottaDB template.
