"""`m engine` subcommand surface — nested verbs over an EngineDriver.

Wires argparse subparsers for each lifecycle verb (status / install /
start / stop / restart / logs / shell / exec / version / reset /
capabilities), dispatches to the active
:class:`m_cli.engine_driver.EngineDriver`, and emits status output in
text or JSON.

The driver itself is resolved by :func:`select_driver` — the built-in
``DockerDriver`` is the only option in core; out-of-tree drivers will
register via the ``m_cli_engines`` entry-point group (Phase 2.3) and
hook in here without touching this file.

See ``m-test-engine/docs/m-engine-implementation-plan.md`` §2.1.
"""

from __future__ import annotations

import argparse
import json
from typing import Callable

from m_cli.engine_driver import DockerDriver, EngineDriver
from m_cli.engine_manifest import load_engine_manifest

# Cached driver factory so tests can inject a fake without touching
# Docker. Production code uses the default (DockerDriver from
# manifest); tests monkeypatch :data:`_DRIVER_FACTORY`.
_DriverFactory = Callable[[], EngineDriver]


def _default_driver_factory() -> EngineDriver:
    manifest = load_engine_manifest()
    return DockerDriver(manifest=manifest)


_DRIVER_FACTORY: _DriverFactory = _default_driver_factory


def set_driver_factory(factory: _DriverFactory) -> None:
    """Override the driver resolution (tests, future entry-point integration)."""
    global _DRIVER_FACTORY
    _DRIVER_FACTORY = factory


def select_driver() -> EngineDriver:
    return _DRIVER_FACTORY()


# ── argparse wiring ──────────────────────────────────────────────────


def add_engine_arguments(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``engine`` subcommand tree on a top-level parser."""
    engine_parser = subparsers.add_parser(
        "engine",
        help="Manage the m-test-engine container (install/start/stop/...)",
        description=(
            "Lifecycle management for the canonical m-test-engine "
            "Docker container. Every verb shells out to docker / docker "
            "compose; configuration is driven by the vendored "
            "dist/m-test-engine.json contract. See `m doctor` for "
            "diagnostics with fix-pointers; `m engine status` is the "
            "single-line health summary."
        ),
    )
    actions = engine_parser.add_subparsers(
        dest="engine_action",
        required=True,
    )

    # status
    status_p = actions.add_parser(
        "status",
        help="Print container/image/daemon state",
    )
    status_p.add_argument("--json", action="store_true", help="Emit JSON")
    status_p.set_defaults(func=_cmd_status)

    # install
    install_p = actions.add_parser(
        "install",
        help="Pull the canonical engine image (`docker pull`)",
    )
    install_p.set_defaults(func=_cmd_install)

    # start
    start_p = actions.add_parser(
        "start",
        help="Start the engine container (compose-first; docker-run fallback)",
    )
    start_p.set_defaults(func=_cmd_start)

    # stop
    stop_p = actions.add_parser(
        "stop",
        help="Stop the engine container (globals volume preserved)",
    )
    stop_p.set_defaults(func=_cmd_stop)

    # restart
    restart_p = actions.add_parser(
        "restart",
        help="Stop + start",
    )
    restart_p.set_defaults(func=_cmd_restart)

    # logs
    logs_p = actions.add_parser(
        "logs",
        help="Print container logs (use --follow to stream)",
    )
    logs_p.add_argument("--follow", "-f", action="store_true", help="Stream logs continuously")
    logs_p.set_defaults(func=_cmd_logs)

    # shell
    shell_p = actions.add_parser(
        "shell",
        help="Interactive bash shell inside the container",
    )
    shell_p.set_defaults(func=_cmd_shell)

    # exec
    exec_p = actions.add_parser(
        "exec",
        help="Run a one-shot M command via `mumps -run %%XCMD`",
    )
    exec_p.add_argument(
        "m_cmd",
        help="M command to execute (e.g. 'write $ZVERSION,!')",
    )
    exec_p.set_defaults(func=_cmd_exec)

    # version
    version_p = actions.add_parser(
        "version",
        help="Print manifest-declared vs container-reported versions",
    )
    version_p.add_argument("--json", action="store_true", help="Emit JSON")
    version_p.set_defaults(func=_cmd_version)

    # reset (destructive)
    reset_p = actions.add_parser(
        "reset",
        help="DESTRUCTIVE: stop + remove + drop globals volume",
        description=(
            "Wipes the running container AND the persistent globals "
            "volume. Useful when a stuck global/lock state poisons "
            "tests. Refuses to run without --confirm."
        ),
    )
    reset_p.add_argument(
        "--confirm",
        action="store_true",
        help="Required acknowledgement that this is destructive",
    )
    reset_p.set_defaults(func=_cmd_reset)

    # capabilities — mirrors top-level `m capabilities`
    caps_p = actions.add_parser(
        "capabilities",
        help="Emit the engine namespace's machine-readable capabilities (JSON)",
    )
    caps_p.set_defaults(func=_cmd_capabilities)


def engine_command(args: argparse.Namespace) -> int:
    """Top-level dispatcher (matches the pattern of every other subcommand)."""
    return args.func(args)


# ── verb handlers ────────────────────────────────────────────────────


def _cmd_status(args: argparse.Namespace) -> int:
    driver = select_driver()
    status = driver.status()
    if getattr(args, "json", False):
        print(json.dumps(status.to_dict(), indent=2))
    else:
        marks = {True: "✓", False: "✗", None: "-"}
        print(f"driver:           {status.driver}")
        print(f"image:            {status.image_ref}")
        print(f"container:        {status.container}")
        print(f"  cli installed:  {marks[status.installed]}")
        print(f"  daemon up:      {marks[status.daemon_reachable]}")
        print(f"  image present:  {marks[status.image_present]}")
        print(f"  container up:   {marks[status.container_running]}")
        print(f"  healthy:        {marks[status.container_healthy]}")
        if status.mismatches:
            print()
            print("⚠ version skew detected:")
            for m in status.mismatches:
                print(f"    {m} — re-pull the image or re-vendor the manifest")
    return 0 if status.container_running else 1


def _cmd_install(args: argparse.Namespace) -> int:
    return select_driver().install()


def _cmd_start(args: argparse.Namespace) -> int:
    return select_driver().start()


def _cmd_stop(args: argparse.Namespace) -> int:
    return select_driver().stop()


def _cmd_restart(args: argparse.Namespace) -> int:
    return select_driver().restart()


def _cmd_logs(args: argparse.Namespace) -> int:
    return select_driver().logs(follow=getattr(args, "follow", False))


def _cmd_shell(args: argparse.Namespace) -> int:
    return select_driver().shell()


def _cmd_exec(args: argparse.Namespace) -> int:
    return select_driver().exec(args.m_cmd)


def _cmd_version(args: argparse.Namespace) -> int:
    return select_driver().version(as_json=getattr(args, "json", False))


def _cmd_reset(args: argparse.Namespace) -> int:
    return select_driver().reset(confirm=args.confirm)


def _cmd_capabilities(args: argparse.Namespace) -> int:
    """Emit the engine namespace as JSON. Mirrors `m capabilities --json`."""
    manifest = load_engine_manifest()
    payload = {
        "namespace": "engine",
        "driver": "docker",
        "manifest": {
            "protocol": manifest.protocol,
            "image": manifest.image,
            "default_tag": manifest.default_tag,
            "image_ref": manifest.image_ref(),
            "container": manifest.container,
            "ydb_version": manifest.ydb_version,
            "bind_mount": {
                "host": manifest.bind_mount.host,
                "container": manifest.bind_mount.container,
                "mode": manifest.bind_mount.mode,
            },
        },
        "verbs": [
            {"name": "status", "destructive": False, "read_only": True},
            {"name": "install", "destructive": False, "read_only": False},
            {"name": "start", "destructive": False, "read_only": False},
            {"name": "stop", "destructive": False, "read_only": False},
            {"name": "restart", "destructive": False, "read_only": False},
            {"name": "logs", "destructive": False, "read_only": True},
            {"name": "shell", "destructive": False, "read_only": False},
            {"name": "exec", "destructive": False, "read_only": False},
            {"name": "version", "destructive": False, "read_only": True},
            {"name": "reset", "destructive": True, "read_only": False, "requires_confirm": True},
            {"name": "capabilities", "destructive": False, "read_only": True},
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


__all__ = [
    "add_engine_arguments",
    "engine_command",
    "select_driver",
    "set_driver_factory",
]
