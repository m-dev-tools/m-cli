"""Tests for the vendored m-test-engine manifest loader.

m-cli vendors `dist/m-test-engine.json` from the m-test-engine repo at
release time. The loader in `m_cli.engine_manifest` is the in-process
source of truth for the engine contract — image registry, container
name, bind-mount layout, compose file path, YDB release.

`m doctor` and (later) `m engine <verb>` consume the loaded manifest;
hardcoded strings in `m_cli.engine.DockerEngine` collapse onto it once
Phase 2 lands.

See docs/m-engine-implementation-plan.md (in the m-test-engine repo)
for the full design rationale and the protocol bump policy.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from m_cli.engine_manifest import (
    BindMount,
    EngineManifest,
    load_engine_manifest,
    vendored_manifest_path,
)


def test_vendored_manifest_path_resolves_to_dist_file():
    p = vendored_manifest_path()
    assert isinstance(p, Path)
    assert p.name == "m-test-engine.json"
    assert p.exists(), "Phase 1b.1 vendoring step must have run"


def test_load_engine_manifest_returns_dataclass():
    m = load_engine_manifest()
    assert isinstance(m, EngineManifest)


def test_manifest_protocol_is_one_at_phase_one():
    m = load_engine_manifest()
    assert m.protocol == 1


def test_manifest_image_ref_combines_image_and_default_tag():
    m = load_engine_manifest()
    assert m.image_ref() == f"{m.image}:{m.default_tag}"


def test_manifest_container_name_matches_existing_DockerEngine_default():
    # Cross-check the manifest matches the legacy hardcoded default in
    # DockerEngine. When Phase 2 collapses the hardcoded value onto the
    # manifest, this assertion still passes — but it documents the
    # consistency requirement during the transition.
    from m_cli.engine import DockerEngine

    m = load_engine_manifest()
    assert m.container == DockerEngine.container


def test_manifest_bind_mount_container_matches_DockerEngine_default():
    # Same drift gate but for bind_root — manifest's bind_mount.container
    # must match DockerEngine's default bind_root. Otherwise a fresh
    # DockerEngine() builds routine paths that don't exist inside the
    # actual running container.
    from m_cli.engine import DockerEngine

    m = load_engine_manifest()
    eng = DockerEngine()
    assert str(eng.bind_root) == m.bind_mount.container


def test_manifest_bind_mount_is_typed():
    m = load_engine_manifest()
    assert isinstance(m.bind_mount, BindMount)
    assert m.bind_mount.host.startswith("/")
    assert m.bind_mount.container.startswith("/")
    assert m.bind_mount.mode in ("ro", "rw")


def test_manifest_compose_file_relative_to_engine_repo():
    m = load_engine_manifest()
    # Compose file path is repo-relative inside m-test-engine, NOT
    # resolvable from m-cli. The contract just declares it; m-cli uses
    # it to construct hints.
    assert m.compose_file
    assert not Path(m.compose_file).is_absolute()


def test_manifest_run_args_carry_fallback_docker_run_payload():
    m = load_engine_manifest()
    args = m.run_args
    assert args.hostname
    assert args.working_dir.startswith("/")
    assert args.restart in ("no", "always", "on-failure", "unless-stopped")
    assert isinstance(args.command, tuple)
    assert all(isinstance(s, str) for s in args.command)


def test_manifest_load_from_explicit_path(tmp_path):
    # Loader accepts an override path — useful for tests and for the
    # future `m engine --manifest=/custom/path` flag.
    payload = {
        "protocol": 1,
        "image": "example/img",
        "default_tag": "v1",
        "container": "x",
        "bind_mount": {"host": "/h", "container": "/c", "mode": "rw"},
        "compose_file": "compose.yml",
        "repo_url": "https://example.com/repo",
        "min_docker": "20.10",
        "ydb_version": "r2.02",
        "run_args": {
            "hostname": "x",
            "working_dir": "/c",
            "restart": "unless-stopped",
            "volumes": [{"name": "v", "target": "/v"}],
            "command": ["sleep", "infinity"],
        },
        "verified_on": "2026-05-11",
    }
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(payload))
    m = load_engine_manifest(p)
    assert m.image == "example/img"
    assert m.image_ref() == "example/img:v1"
    assert m.bind_mount.container == "/c"


def test_manifest_load_missing_required_field_raises(tmp_path):
    payload = {"protocol": 1}  # everything else missing
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(payload))
    with pytest.raises((KeyError, TypeError, ValueError)):
        load_engine_manifest(p)


def test_manifest_load_unknown_protocol_version_raises(tmp_path):
    payload_base = {
        "protocol": 999,  # higher than anything m-cli understands
        "image": "x",
        "default_tag": "y",
        "container": "z",
        "bind_mount": {"host": "/h", "container": "/c", "mode": "rw"},
        "compose_file": "compose.yml",
        "repo_url": "https://example.com",
        "min_docker": "20.10",
        "ydb_version": "r2.02",
        "run_args": {
            "hostname": "x",
            "working_dir": "/c",
            "restart": "unless-stopped",
            "volumes": [],
            "command": ["sleep", "infinity"],
        },
        "verified_on": "2026-05-11",
    }
    p = tmp_path / "future.json"
    p.write_text(json.dumps(payload_base))
    with pytest.raises(ValueError, match="protocol"):
        load_engine_manifest(p)
