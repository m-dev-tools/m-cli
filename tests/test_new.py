"""Tests for m new — project scaffolder.

`m new <name>` creates a self-contained M project that passes
`m fmt --check`, `m lint`, and `m test` on a clean clone. Ships:

  <name>/
  ├── routines/<NAME>.m         starter routine (pythonic-lower)
  ├── routines/<NAME>ASRT.m     tiny self-contained assertion helper
  ├── tests/<NAME>TST.m         starter test suite
  ├── .m-cli.toml               pythonic-lower fmt + modern lint
  ├── .gitignore                .venv, __pycache__, *.o, coverage.lcov
  ├── Makefile                  fmt / lint / test / coverage / check
  └── README.md                 minimal scaffold blurb

The routine name is the project name uppercased and stripped of
non-alphanumeric characters; truncated to 8 chars (M routine-name limit).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from m_cli.fmt import format_source, select_fmt_rules
from m_cli.lint import lint_source, select_rules
from m_cli.new import new_command
from m_cli.new.scaffold import (
    Scaffold,
    derive_routine_name,
    render_scaffold,
)

# -------------------------------------------------------- routine-name derivation


def test_derive_routine_name_uppercases():
    assert derive_routine_name("hello") == "HELLO"


def test_derive_routine_name_strips_non_alnum():
    assert derive_routine_name("hello-world") == "HELLOWOR"  # hyphens stripped, 8-char cap
    assert derive_routine_name("my_app_v2") == "MYAPPV2"


def test_derive_routine_name_truncates_to_eight():
    assert derive_routine_name("supercalifragilistic") == "SUPERCAL"


def test_derive_routine_name_rejects_empty():
    import pytest

    with pytest.raises(ValueError):
        derive_routine_name("")
    with pytest.raises(ValueError):
        derive_routine_name("---")


def test_derive_routine_name_rejects_leading_digit():
    import pytest

    with pytest.raises(ValueError):
        derive_routine_name("1bad")


# ----------------------------------------------------------------- render_scaffold


def test_render_scaffold_returns_file_map():
    s = render_scaffold("hello")
    assert isinstance(s, Scaffold)
    assert s.routine_name == "HELLO"
    paths = set(s.files.keys())
    expected = {
        "routines/HELLO.m",
        "routines/HELLOASRT.m",
        "tests/HELLOTST.m",
        ".m-cli.toml",
        ".gitignore",
        "Makefile",
        "README.md",
    }
    assert expected.issubset(paths)


def test_render_scaffold_routine_starts_with_routine_name():
    s = render_scaffold("greeter")
    rtn = s.files["routines/GREETER.m"]
    # Line 1's first token must be the routine name (M convention)
    first_line = rtn.splitlines()[0]
    assert first_line.startswith("GREETER")


def test_render_scaffold_test_calls_routine():
    s = render_scaffold("greeter")
    test = s.files["tests/GREETERTST.m"]
    assert "^GREETER" in test  # references the production routine
    assert "^GREETERASRT" in test  # uses the bundled assertion helper


def test_render_scaffold_mcli_toml_is_pythonic_lower():
    s = render_scaffold("hello")
    toml = s.files[".m-cli.toml"]
    assert "pythonic-lower" in toml
    assert "[fmt]" in toml
    assert "[lint]" in toml


def test_render_scaffold_makefile_uses_m_subcommands():
    s = render_scaffold("hello")
    mk = s.files["Makefile"]
    # Makefile uses `$(M) <subcommand>` so `M=` is overridable.
    assert "$(M) fmt" in mk
    assert "$(M) lint" in mk
    assert "$(M) test" in mk
    assert "$(M) coverage" in mk


def test_render_scaffold_gitignore_covers_common_artifacts():
    s = render_scaffold("hello")
    gi = s.files[".gitignore"]
    assert "*.o" in gi
    assert "coverage.lcov" in gi
    assert ".venv" in gi


# ----------------------------------------------------- generated content gates


def test_generated_routine_passes_fmt_canonical():
    """Generated routine round-trips identically through canonical fmt."""
    s = render_scaffold("hello")
    src = s.files["routines/HELLO.m"]
    out = format_source(src.encode(), rules=select_fmt_rules("pythonic-lower"))
    assert out.decode() == src


def test_generated_test_passes_fmt_canonical():
    s = render_scaffold("hello")
    src = s.files["tests/HELLOTST.m"]
    out = format_source(src.encode(), rules=select_fmt_rules("pythonic-lower"))
    assert out.decode() == src


def test_generated_routine_has_no_lint_errors():
    """Default profile: no ERROR-severity findings on the generated routine."""
    s = render_scaffold("hello")
    src = s.files["routines/HELLO.m"]
    rules = select_rules("default")
    diags = lint_source(Path("scaffold.m"), src.encode(), rules)
    errors = [d for d in diags if d.severity.name == "ERROR"]
    assert errors == [], f"unexpected lint errors: {errors}"


def test_generated_test_has_no_lint_errors():
    s = render_scaffold("hello")
    src = s.files["tests/HELLOTST.m"]
    rules = select_rules("default")
    diags = lint_source(Path("scaffold.m"), src.encode(), rules)
    errors = [d for d in diags if d.severity.name == "ERROR"]
    assert errors == [], f"unexpected lint errors: {errors}"


def test_generated_assertion_helper_has_no_lint_errors():
    s = render_scaffold("hello")
    src = s.files["routines/HELLOASRT.m"]
    rules = select_rules("default")
    diags = lint_source(Path("scaffold.m"), src.encode(), rules)
    errors = [d for d in diags if d.severity.name == "ERROR"]
    assert errors == [], f"unexpected lint errors: {errors}"


# ------------------------------------------------------------- CLI behaviour


def _ns(**kw) -> argparse.Namespace:
    base = {"name": "demo", "path": None, "force": False, "quiet": True}
    base.update(kw)
    return argparse.Namespace(**base)


def test_new_command_creates_project(tmp_path):
    rc = new_command(_ns(name="hello", path=tmp_path / "hello"))
    assert rc == 0
    root = tmp_path / "hello"
    assert (root / "routines" / "HELLO.m").is_file()
    assert (root / "tests" / "HELLOTST.m").is_file()
    assert (root / ".m-cli.toml").is_file()
    assert (root / "Makefile").is_file()


def test_new_command_refuses_existing_dir(tmp_path):
    target = tmp_path / "hello"
    target.mkdir()
    (target / "preexisting.txt").write_text("keep me")
    rc = new_command(_ns(name="hello", path=target))
    assert rc != 0
    # Existing file untouched
    assert (target / "preexisting.txt").read_text() == "keep me"


def test_new_command_force_overwrites(tmp_path):
    target = tmp_path / "hello"
    target.mkdir()
    rc = new_command(_ns(name="hello", path=target, force=True))
    assert rc == 0
    assert (target / "routines" / "HELLO.m").is_file()


def test_new_command_default_path_uses_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = new_command(_ns(name="hello", path=None))
    assert rc == 0
    assert (tmp_path / "hello" / "routines" / "HELLO.m").is_file()


def test_new_command_invalid_name_returns_nonzero(tmp_path):
    rc = new_command(_ns(name="123bad", path=tmp_path / "x"))
    assert rc != 0
