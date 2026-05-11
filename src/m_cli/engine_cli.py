"""`m engine` subcommand surface — nested verbs over an EngineDriver.

Wires argparse subparsers for each lifecycle verb (status / install /
start / stop / restart / logs / shell / exec / version / upgrade /
reset / capabilities), dispatches to the active
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
    status_p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help=(
            "Additionally run `mte status --json` inside the container "
            "and fold release / uptime / globals / routines / mounted-"
            "repos into the report. Surfaces runtime YDB-version drift "
            "that the static-label check can't catch."
        ),
    )
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
    version_p.set_defaults(func=_cmd_version)

    # upgrade
    upgrade_p = actions.add_parser(
        "upgrade",
        help="Pull latest image and recreate container (globals preserved)",
    )
    upgrade_p.set_defaults(func=_cmd_upgrade)

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

    # watch — long-running poll of mte status --json
    watch_p = actions.add_parser(
        "watch",
        help="Stream mte status --json on an interval (Ctrl+C to stop)",
        description=(
            "Long-running poll of `mte status --json` inside the "
            "container. Emits one JSON-lines record per poll. Useful "
            "for live monitoring during long test runs or for tailing "
            "engine state from a CI log. Ctrl+C exits cleanly."
        ),
    )
    watch_p.add_argument(
        "--interval",
        "-n",
        type=float,
        default=5.0,
        help="Seconds between polls (default: 5.0)",
    )
    watch_p.add_argument(
        "--count",
        type=int,
        default=0,
        help="Stop after N polls. 0 (default) = run until Ctrl+C.",
    )
    watch_p.set_defaults(func=_cmd_watch)

    # capabilities — mirrors top-level `m capabilities`
    caps_p = actions.add_parser(
        "capabilities",
        help="Emit the engine namespace's machine-readable capabilities",
    )
    caps_p.add_argument("--json", action="store_true", help="JSON (default: pretty-printed JSON)")
    caps_p.set_defaults(func=_cmd_capabilities)


def engine_command(args: argparse.Namespace) -> int:
    """Top-level dispatcher (matches the pattern of every other subcommand)."""
    return args.func(args)


# ── verb handlers ────────────────────────────────────────────────────


def _cmd_status(args: argparse.Namespace) -> int:
    driver = select_driver()
    verbose = getattr(args, "verbose", False)
    status = driver.status(verbose=verbose)
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
        # Phase 4b: fold mte status payload when --verbose.
        if verbose and status.mte is not None:
            print()
            print("inside container (mte):")
            print(f"  release:        {status.mte.get('release', '?')}")
            print(f"  uptime:         {status.mte.get('uptime_s', '?')}s")
            print(f"  globals_count:  {status.mte.get('globals_count', '?')}")
            print(f"  routines_count: {status.mte.get('routines_count', '?')}")
            repos = status.mte.get("mounted_repos", []) or []
            print(f"  mounted_repos:  {', '.join(repos) if repos else '(none)'}")
        elif verbose and status.container_running:
            print()
            print("⚠ mte status --json failed inside the container (script missing or error)")
        # Phase 3b: surface label-vs-manifest mismatches as WARN lines.
        # Each mismatch class has an actionable next step.
        if status.mismatches:
            print()
            print("⚠ version skew detected:")
            for m in status.mismatches:
                print(f"    {m} — run `m engine upgrade` or re-vendor the manifest")
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
    return select_driver().version()


def _cmd_upgrade(args: argparse.Namespace) -> int:
    return select_driver().upgrade()


def _cmd_reset(args: argparse.Namespace) -> int:
    return select_driver().reset(confirm=args.confirm)


def _cmd_watch(args: argparse.Namespace) -> int:
    """Long-running poll of ``mte status --json``.

    Emits one JSON-lines record per poll (each line is a self-contained
    ``mte`` payload plus a ``ts`` field with the wall-clock timestamp).
    Exits cleanly on Ctrl+C / SIGINT. ``--count N`` caps the poll loop
    at N iterations (useful for tests + bounded CI checks); the default
    ``0`` means "run until interrupted".

    Phase 4b.2 of the m-engine plan.
    """
    import time

    driver = select_driver()
    interval = max(0.1, float(getattr(args, "interval", 5.0)))
    count = int(getattr(args, "count", 0))
    emitted = 0
    try:
        while count == 0 or emitted < count:
            payload = driver.mte_status()
            line: dict = {"ts": time.time()}
            if payload is None:
                line["error"] = "mte_status returned no payload (container down or mte missing)"
            else:
                line.update(payload)
            print(json.dumps(line), flush=True)
            emitted += 1
            if count and emitted >= count:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        # Clean exit — stop without traceback or rc-130.
        return 0
    return 0


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
            {"name": "upgrade", "destructive": False, "read_only": False},
            {"name": "reset", "destructive": True, "read_only": False, "requires_confirm": True},
            {"name": "watch", "destructive": False, "read_only": True},
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
