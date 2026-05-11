"""Runtime probes used by Docker-engine checks in ``m doctor``.

These functions wrap the shell-out / filesystem calls that determine
whether the Docker engine path is healthy. They live in their own
module so tests can monkeypatch them without faking ``subprocess`` or
``shutil`` at large.

Failure modes are intentionally non-throwing: every probe returns
``bool``. The diagnostic richness (which exact failure occurred) is
handled by the check function that wraps the probe.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_TIMEOUT_SECONDS = 5


def docker_available() -> bool:
    """``docker`` CLI is on ``PATH``."""
    return shutil.which("docker") is not None


def docker_daemon_reachable() -> bool:
    """``docker info`` returns 0 — the daemon is up and accessible."""
    if not docker_available():
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=_TIMEOUT_SECONDS,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def docker_image_present(ref: str) -> bool:
    """``docker image inspect <ref>`` returns 0 — image is pulled locally."""
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", ref],
            capture_output=True,
            timeout=_TIMEOUT_SECONDS,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def docker_container_running(name: str) -> bool:
    """A container with this exact name is in ``docker ps`` output."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
            capture_output=True,
            timeout=_TIMEOUT_SECONDS,
            text=True,
        )
        if result.returncode != 0:
            return False
        return name in result.stdout.split()
    except (subprocess.TimeoutExpired, OSError):
        return False


def path_exists(path: str) -> bool:
    """Host filesystem path resolves."""
    return Path(path).exists()
