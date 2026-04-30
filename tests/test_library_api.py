"""Library API smoke test — locks the public surface for tooling consumers.

Anything imported here is a **public, supported import path** that the
LSP wrapper, IDE plugins, pre-commit integrations, and any other
out-of-tree tooling can depend on. If a future refactor needs to move
a symbol, it must keep the existing alias in place (or this test
breaks and the change is intentional).

The convention is:

    from m_cli import parse, format_source, lint_source, Diagnostic, Severity

Everything reachable from the top-level ``m_cli`` package is the
"surface" we promise to keep stable.
"""

from __future__ import annotations


def test_top_level_parse_importable() -> None:
    from m_cli import parse

    assert callable(parse)


def test_top_level_format_source_importable() -> None:
    from m_cli import format_source

    assert callable(format_source)


def test_top_level_lint_source_importable() -> None:
    from m_cli import lint_source

    assert callable(lint_source)


def test_top_level_diagnostic_and_severity_importable() -> None:
    from m_cli import Category, Diagnostic, Severity

    assert hasattr(Severity, "ERROR")
    assert hasattr(Severity, "WARNING")
    assert hasattr(Severity, "STYLE")
    assert hasattr(Severity, "INFO")
    assert hasattr(Category, "BUG")
    assert hasattr(Diagnostic, "__annotations__")


def test_top_level_lint_helpers_importable() -> None:
    from m_cli import Rule, select_rules

    assert callable(select_rules)
    assert hasattr(Rule, "__annotations__")


def test_top_level_fmt_helpers_importable() -> None:
    from m_cli import FmtRule, canonical_rules, select_fmt_rules

    assert callable(canonical_rules)
    assert callable(select_fmt_rules)
    assert hasattr(FmtRule, "__annotations__")


def test_top_level_translation_presets_importable() -> None:
    from m_cli import compact_rules, pythonic_rules

    assert callable(pythonic_rules)
    assert callable(compact_rules)
    assert {r.id for r in pythonic_rules()} & {r.id for r in compact_rules()} == {
        "trim-trailing-whitespace"
    }


def test_top_level_parse_error_importable() -> None:
    from m_cli import ParseError

    assert issubclass(ParseError, Exception)


def test_subpackage_lint_surface() -> None:
    from m_cli.lint import (
        Category,
        Diagnostic,
        Rule,
        Severity,
        lint_source,
        select_rules,
    )

    assert callable(lint_source)
    assert callable(select_rules)
    assert hasattr(Severity, "ERROR")
    assert hasattr(Category, "BUG")
    assert hasattr(Diagnostic, "__annotations__")
    assert hasattr(Rule, "__annotations__")


def test_subpackage_fmt_surface() -> None:
    from m_cli.fmt import (
        FmtRule,
        ParseError,
        canonical_rules,
        format_file,
        format_source,
        select_fmt_rules,
    )

    assert callable(format_source)
    assert callable(format_file)
    assert callable(canonical_rules)
    assert callable(select_fmt_rules)
    assert hasattr(FmtRule, "__annotations__")
    assert issubclass(ParseError, Exception)


def test_subpackage_parser_surface() -> None:
    from m_cli.parser import parse

    assert callable(parse)


def test_top_level_all_lists_every_advertised_symbol() -> None:
    """Anything we promise downstream consumers is in __all__."""
    import m_cli

    expected = {
        "parse",
        "format_source",
        "lint_source",
        "Diagnostic",
        "Severity",
        "Rule",
        "FmtRule",
        "select_rules",
        "select_fmt_rules",
        "canonical_rules",
        "ParseError",
        "__version__",
    }
    missing = expected - set(m_cli.__all__)
    assert not missing, f"top-level __all__ missing: {missing}"


def test_lint_subpackage_all_includes_Rule() -> None:
    import m_cli.lint as lint_mod

    assert "Rule" in lint_mod.__all__
    assert "select_rules" in lint_mod.__all__


def test_fmt_subpackage_all_includes_canonical_helpers() -> None:
    import m_cli.fmt as fmt_mod

    for name in ("canonical_rules", "select_fmt_rules", "FmtRule"):
        assert name in fmt_mod.__all__, f"fmt __all__ missing {name}"


def test_one_import_round_trips_a_routine() -> None:
    """End-to-end smoke: parse → lint → format using only public imports."""
    from m_cli import canonical_rules, format_source, lint_source, parse, select_rules

    src = b"hello ;c\n new x\n quit\n"
    tree = parse(src)
    assert tree is not None

    diags = lint_source(__import__("pathlib").Path("hello.m"), src, select_rules("xindex"))
    # Real diagnostics from existing rules; we just want non-failure import.
    assert isinstance(diags, list)

    out = format_source(src, rules=canonical_rules())
    # Canonical fmt uppercases keywords on this sample.
    assert b"NEW x" in out
    assert b"QUIT" in out
