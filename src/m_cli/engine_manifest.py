"""In-process loader for the vendored m-test-engine manifest.

m-cli vendors ``dist/m-test-engine.json`` from the m-test-engine repo at
release time (see Makefile's ``manifest`` target). This module parses
that file into typed dataclasses and is the single in-process source of
truth for the engine contract: image registry, container name,
bind-mount layout, compose file path, YDB release.

Consumed by:

* ``m doctor`` — emits actionable Docker-engine hints derived from
  these fields (Phase 1b).
* The ``m engine`` subcommand family — builds ``docker`` /
  ``docker compose`` invocations from these fields (Phase 2).

The legacy hardcoded constants in :class:`m_cli.engine.DockerEngine`
(``container = "m-test-engine"`` / ``bind_root = /work``) are kept in
sync with this manifest during the Phase 1 → Phase 2 transition.

Protocol handshake — see ``docs/m-engine-implementation-plan.md`` §1.5
in the m-test-engine repo for the bump policy. m-cli understands a
fixed set of protocol versions and rejects manifests claiming a higher
one, with a clear "upgrade m-cli" hint.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def _expand_host_path(raw: str) -> str:
    """Expand ``$HOME`` / ``~`` in a manifest host-side path.

    Workspace convention (see ``m-dev-tools/CLAUDE.md`` § 6): host paths
    declared by m-* repos are rooted in ``$HOME`` (e.g.
    ``$HOME/m-work``). Consumers expand at runtime so the same vendored
    contract works across users. Container-side paths stay absolute.

    Plain absolute paths (e.g. ``/m-work``) pass through unchanged so
    legacy / custom layouts still work.
    """
    return os.path.expanduser(os.path.expandvars(raw))

# Protocol versions this build of m-cli can consume. Add to this set
# when a new protocol revision is adopted; never remove an entry until
# the corresponding manifest version is provably gone from the wild.
SUPPORTED_PROTOCOLS: frozenset[int] = frozenset({1})


@dataclass(frozen=True)
class BindMount:
    host: str
    container: str
    mode: str


@dataclass(frozen=True)
class Volume:
    name: str
    target: str


@dataclass(frozen=True)
class RunArgs:
    hostname: str
    working_dir: str
    restart: str
    volumes: tuple[Volume, ...]
    command: tuple[str, ...]


@dataclass(frozen=True)
class EngineManifest:
    protocol: int
    image: str
    default_tag: str
    container: str
    bind_mount: BindMount
    compose_file: str
    repo_url: str
    min_docker: str
    ydb_version: str
    run_args: RunArgs
    verified_on: str

    def image_ref(self) -> str:
        """Full image reference including tag (e.g. ``ghcr.io/...:r2.02``)."""
        return f"{self.image}:{self.default_tag}"


def vendored_manifest_path() -> Path:
    """Absolute path to the vendored manifest inside this m-cli checkout."""
    # src/m_cli/engine_manifest.py → repo_root/dist/m-test-engine.json
    return Path(__file__).resolve().parent.parent.parent / "dist" / "m-test-engine.json"


def load_engine_manifest(path: Path | None = None) -> EngineManifest:
    """Parse the manifest into an :class:`EngineManifest`.

    Pass ``path`` to load from a non-default location (tests, the future
    ``m engine --manifest=...`` flag). Raises ``FileNotFoundError`` if
    the file does not exist, ``ValueError`` for protocol mismatches or
    malformed structures, and ``KeyError`` for missing required fields.
    """
    src = path if path is not None else vendored_manifest_path()
    data = json.loads(src.read_text(encoding="utf-8"))

    protocol = data["protocol"]
    if not isinstance(protocol, int):
        raise ValueError(f"protocol must be an integer, got {type(protocol).__name__}")
    if protocol not in SUPPORTED_PROTOCOLS:
        supported = sorted(SUPPORTED_PROTOCOLS)
        raise ValueError(
            f"manifest protocol {protocol} is not supported by this "
            f"build of m-cli (supports: {supported}). "
            "Upgrade m-cli or vendor a compatible manifest."
        )

    bm = data["bind_mount"]
    bind_mount = BindMount(
        host=_expand_host_path(bm["host"]),
        container=bm["container"],
        mode=bm["mode"],
    )

    ra = data["run_args"]
    volumes = tuple(Volume(name=v["name"], target=v["target"]) for v in ra["volumes"])
    run_args = RunArgs(
        hostname=ra["hostname"],
        working_dir=ra["working_dir"],
        restart=ra["restart"],
        volumes=volumes,
        command=tuple(ra["command"]),
    )

    return EngineManifest(
        protocol=protocol,
        image=data["image"],
        default_tag=data["default_tag"],
        container=data["container"],
        bind_mount=bind_mount,
        compose_file=data["compose_file"],
        repo_url=data["repo_url"],
        min_docker=data["min_docker"],
        ydb_version=data["ydb_version"],
        run_args=run_args,
        verified_on=data["verified_on"],
    )
