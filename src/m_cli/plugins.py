"""Out-of-tree subcommand discovery via Python entry-points.

m-cli's built-in subcommands are wired by name in ``cli.py``. To extend
the toolchain without modifying core, third-party packages can register
subcommands via the ``m_cli.plugins`` entry-point group::

    [project.entry-points."m_cli.plugins"]
    bench = "m_cli_extras.bench:register"
    diff  = "m_cli_extras.diff:register"

The named function (here ``m_cli_extras.bench:register``) is called
once during ``m`` startup with the dispatcher's ``subparsers`` argument.
The plugin function is expected to do the same dance every built-in
subcommand does:

    def register(subparsers) -> None:
        sp = subparsers.add_parser("bench", help="...")
        sp.add_argument(...)
        sp.set_defaults(func=bench_command)

The plugin may import any name from the top-level ``m_cli`` public
surface (``parse``, ``lint_source``, ``format_source``, ``Diagnostic``,
…) — those are pinned by ``tests/test_library_api.py``.

Hard rules:

- A plugin whose name collides with a built-in subcommand is rejected
  silently-but-reported (``m plugins`` lists it under ``conflicts``).
  Built-ins always win — no override.
- A plugin whose ``register()`` raises is rejected the same way.
  Other plugins keep loading.
- Two plugins claiming the same name: first one wins by enumeration
  order; the second is reported as a conflict.

For the contract version + the consumer-side template, see
``docs/plugin-development.md``.
"""

from __future__ import annotations

import importlib.metadata as _md
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

# The entry-point group consumers declare against.
ENTRY_POINT_GROUP = "m_cli.plugins"

# Bumped when the plugin contract changes in a backwards-incompatible
# way. Plugins SHOULD declare which version they target so a future
# m-cli can refuse loading mismatched plugins. Today we don't enforce.
PLUGIN_API_VERSION = 1


@dataclass(frozen=True)
class PluginInfo:
    """Metadata about a discovered plugin.

    Used for `m plugins` introspection and conflict reporting.
    """

    name: str
    """Subcommand name the plugin exposes (e.g. ``bench``)."""

    package: str
    """Source package that ships the plugin (e.g. ``m_cli_extras``)."""

    version: str
    """Source-package version reported by the dist."""

    entry_point: str
    """Full entry-point spec (``module:attr``)."""


class PluginRegistration(Protocol):
    """Function signature every plugin's entry-point must satisfy."""

    def __call__(self, subparsers) -> None: ...


def _iter_entry_points() -> Iterable[_md.EntryPoint]:
    """Walk every entry-point in the ``m_cli.plugins`` group.

    Wrapped so tests can monkeypatch in fakes without going through
    ``importlib.metadata``.
    """
    return _md.entry_points(group=ENTRY_POINT_GROUP)


def _package_name(ep: _md.EntryPoint) -> str:
    """Resolve the dist name that owns this entry-point. Best-effort."""
    dist = getattr(ep, "dist", None)
    if dist is not None and getattr(dist, "name", None):
        return dist.name
    # Fallback for fakes / older importlib: use the module prefix.
    return ep.value.split(":", 1)[0].split(".", 1)[0]


def _package_version(ep: _md.EntryPoint) -> str:
    """Resolve the dist version. Returns ``unknown`` if not in metadata."""
    dist = getattr(ep, "dist", None)
    if dist is not None and getattr(dist, "version", None):
        return dist.version
    return "unknown"


def discover_plugins() -> list[PluginInfo]:
    """Return metadata for every plugin entry-point installed."""
    return [
        PluginInfo(
            name=ep.name,
            package=_package_name(ep),
            version=_package_version(ep),
            entry_point=ep.value,
        )
        for ep in _iter_entry_points()
    ]


def register_plugins(
    subparsers,
    builtins: set[str],
) -> tuple[list[PluginInfo], list[tuple[str, str]]]:
    """Register every installed plugin's subcommand against ``subparsers``.

    Returns a pair ``(registered, conflicts)``:

    - ``registered`` — :class:`PluginInfo` for every plugin successfully
      attached to the dispatcher.
    - ``conflicts`` — list of ``(name, reason)`` for plugins that were
      skipped (built-in collision, register raised, duplicate name).

    Built-ins always win. Plugins are processed in enumeration order;
    later entry-points cannot displace earlier ones.
    """
    registered: list[PluginInfo] = []
    conflicts: list[tuple[str, str]] = []
    claimed: set[str] = set(builtins)

    for ep in _iter_entry_points():
        name = ep.name

        if name in builtins:
            conflicts.append(
                (name, f"name collides with built-in '{name}' subcommand")
            )
            continue

        if name in claimed:
            conflicts.append(
                (name, f"another plugin already registered subcommand '{name}'")
            )
            continue

        try:
            register_fn = ep.load()
        except Exception as exc:  # noqa: BLE001 — protect dispatcher
            conflicts.append((name, f"failed to load plugin entry-point: {exc!r}"))
            continue

        try:
            register_fn(subparsers)
        except Exception as exc:  # noqa: BLE001 — protect dispatcher
            conflicts.append((name, f"plugin register() raised: {exc!r}"))
            continue

        registered.append(
            PluginInfo(
                name=name,
                package=_package_name(ep),
                version=_package_version(ep),
                entry_point=ep.value,
            )
        )
        claimed.add(name)

    return registered, conflicts


def plugins_command(args) -> int:
    """Handler for ``m plugins`` — introspect installed plugins.

    Reads the registered + conflict lists stashed on the parser by the
    main dispatcher (see ``cli.py``). Falls back to a fresh discovery
    if those defaults aren't populated (defensive).
    """
    registered = getattr(args, "_plugin_registered", None)
    conflicts = getattr(args, "_plugin_conflicts", None)
    if registered is None or conflicts is None:
        # Defensive fallback — emit fresh discovery without registering.
        registered = discover_plugins()
        conflicts = []

    if getattr(args, "json", False):
        import json as _json

        out = {
            "api_version": PLUGIN_API_VERSION,
            "registered": [
                {
                    "name": p.name,
                    "package": p.package,
                    "version": p.version,
                    "entry_point": p.entry_point,
                }
                for p in registered
            ],
            "conflicts": [
                {"name": name, "reason": reason} for name, reason in conflicts
            ],
        }
        print(_json.dumps(out, indent=2))
        return 0

    print(f"m-cli plugin API v{PLUGIN_API_VERSION}")
    print()
    if not registered:
        print("Registered plugins: (none)")
    else:
        print(f"Registered plugins ({len(registered)}):")
        for p in registered:
            print(f"  m {p.name:14s}  ({p.package} {p.version})")
    if conflicts:
        print()
        print(f"Conflicts ({len(conflicts)}):")
        for name, reason in conflicts:
            print(f"  {name:14s}  {reason}")
    return 0


__all__ = [
    "ENTRY_POINT_GROUP",
    "PLUGIN_API_VERSION",
    "PluginInfo",
    "PluginRegistration",
    "discover_plugins",
    "plugins_command",
    "register_plugins",
]
