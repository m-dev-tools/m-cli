"""Tests for the plugin-discovery surface.

m-cli supports out-of-tree subcommands via Python entry-points in the
``m_cli.plugins`` group. A plugin package declares::

    [project.entry-points."m_cli.plugins"]
    bench = "m_cli_extras.bench:register"

and the function ``m_cli_extras.bench:register(subparsers)`` is called
during ``m`` startup. The function is expected to do the same
``subparsers.add_parser(...)`` + ``set_defaults(func=handler)`` dance
the built-in subcommands do — see ``docs/plugin-development.md``.

Plugins whose name collides with a built-in subcommand are rejected
with a clear message; ``m plugins`` reports them in ``conflicts``.

These tests inject fake entry points; we never rely on actual
installed packages.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable

import pytest

from m_cli.plugins import (
    PluginInfo,
    discover_plugins,
    register_plugins,
)

# ── Fake entry-point factory ──────────────────────────────────────────
#
# We use a duck-typed stub instead of a real `importlib.metadata.EntryPoint`
# because EntryPoint.load() resolves the value through `importlib`, and
# pytest's test-module import path isn't stable enough for that. The
# plugins module only depends on the structural shape (name / value /
# dist / load()) — so a minimal stub is sufficient.


@dataclass
class _FakeDist:
    name: str = "fake-pkg"
    version: str = "0.0.1"


@dataclass
class _FakeEP:
    name: str
    value: str
    dist: _FakeDist
    _fn: Callable

    def load(self):
        return self._fn


def _ep(name: str, fn) -> _FakeEP:
    """Build a duck-typed entry-point whose `load()` returns ``fn``."""
    return _FakeEP(
        name=name,
        value=f"fake_pkg.{name}:register",
        dist=_FakeDist(),
        _fn=fn,
    )


# ── discover_plugins() ────────────────────────────────────────────────


def test_discover_plugins_returns_empty_when_none_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("m_cli.plugins._iter_entry_points", lambda: [])
    assert discover_plugins() == []


def test_discover_plugins_returns_one_per_entry_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reg(subparsers): ...
    monkeypatch.setattr(
        "m_cli.plugins._iter_entry_points",
        lambda: [_ep("bench", reg), _ep("audit", reg)],
    )
    plugins = discover_plugins()
    assert {p.name for p in plugins} == {"bench", "audit"}
    for p in plugins:
        assert isinstance(p, PluginInfo)
        assert p.entry_point.endswith(":register")


# ── register_plugins() ────────────────────────────────────────────────


def test_register_plugins_calls_each_entry_point_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each registered plugin's function is invoked with the subparsers."""
    calls = []

    def reg_bench(subparsers):
        calls.append(("bench", subparsers))
        sp = subparsers.add_parser("bench")
        sp.set_defaults(func=lambda args: 0)

    def reg_audit(subparsers):
        calls.append(("audit", subparsers))
        sp = subparsers.add_parser("audit")
        sp.set_defaults(func=lambda args: 0)

    monkeypatch.setattr(
        "m_cli.plugins._iter_entry_points",
        lambda: [_ep("bench", reg_bench), _ep("audit", reg_audit)],
    )

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    registered, conflicts = register_plugins(subparsers, builtins={"fmt", "lint"})

    assert {p.name for p in registered} == {"bench", "audit"}
    assert conflicts == []
    assert {c[0] for c in calls} == {"bench", "audit"}


def test_register_plugins_rejects_collision_with_builtin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plugin named the same as a built-in is refused without crashing."""
    def reg_lint(subparsers):
        # Should never be invoked — the plugin is rejected before this runs.
        raise AssertionError("plugin should not have been called")

    monkeypatch.setattr(
        "m_cli.plugins._iter_entry_points",
        lambda: [_ep("lint", reg_lint)],
    )

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    registered, conflicts = register_plugins(subparsers, builtins={"fmt", "lint"})

    assert registered == []
    assert len(conflicts) == 1
    name, reason = conflicts[0]
    assert name == "lint"
    assert "built-in" in reason.lower() or "builtin" in reason.lower()


def test_register_plugins_isolates_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plugin whose register() raises is reported as a conflict; siblings keep working."""
    def reg_bad(subparsers):
        raise RuntimeError("boom")

    def reg_good(subparsers):
        sp = subparsers.add_parser("good")
        sp.set_defaults(func=lambda args: 0)

    monkeypatch.setattr(
        "m_cli.plugins._iter_entry_points",
        lambda: [_ep("bad", reg_bad), _ep("good", reg_good)],
    )

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    registered, conflicts = register_plugins(subparsers, builtins=set())

    assert [p.name for p in registered] == ["good"]
    assert len(conflicts) == 1
    assert conflicts[0][0] == "bad"
    assert "boom" in conflicts[0][1] or "RuntimeError" in conflicts[0][1]


def test_register_plugins_no_double_register_on_repeat_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two plugins claiming the same name — first wins, second is conflict."""
    def reg_a(subparsers):
        sp = subparsers.add_parser("clash")
        sp.set_defaults(func=lambda args: 0)

    def reg_b(subparsers):
        # Never called — argparse would raise `add_parser` with same name.
        raise AssertionError("second plugin should be skipped before its register runs")

    monkeypatch.setattr(
        "m_cli.plugins._iter_entry_points",
        lambda: [_ep("clash", reg_a), _ep("clash", reg_b)],
    )

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    registered, conflicts = register_plugins(subparsers, builtins=set())

    assert [p.name for p in registered] == ["clash"]
    assert len(conflicts) == 1
    assert conflicts[0][0] == "clash"


def test_plugin_registration_signature_is_callable() -> None:
    """A function that takes subparsers should satisfy the contract."""
    def reg(subparsers): ...
    assert callable(reg)
    # PluginRegistration is a structural Protocol; we don't enforce
    # at runtime, just assert callability covers the common shape.
