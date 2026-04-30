"""Tests for ``m_cli.config`` — project config discovery and parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from m_cli.config import (
    CONFIG_FILENAME,
    PYPROJECT_FILENAME,
    Config,
    find_config,
    load_config,
)
from m_cli.lint.diagnostic import Severity

# ---------------------------------------------------------------------------
# find_config
# ---------------------------------------------------------------------------


def test_find_config_returns_local_m_cli_toml(tmp_path: Path) -> None:
    cfg = tmp_path / CONFIG_FILENAME
    cfg.write_text("[lint]\nrules = 'all'\n", encoding="utf-8")

    assert find_config(tmp_path) == cfg


def test_find_config_walks_up_to_parent(tmp_path: Path) -> None:
    parent = tmp_path / "proj"
    nested = parent / "src" / "deep"
    nested.mkdir(parents=True)
    cfg = parent / CONFIG_FILENAME
    cfg.write_text("[lint]\nrules = 'all'\n", encoding="utf-8")

    assert find_config(nested) == cfg


def test_find_config_prefers_m_cli_toml_over_pyproject(tmp_path: Path) -> None:
    (tmp_path / CONFIG_FILENAME).write_text("[lint]\nrules = 'all'\n", encoding="utf-8")
    (tmp_path / PYPROJECT_FILENAME).write_text(
        "[tool.m-cli]\n[tool.m-cli.lint]\nrules = 'sac'\n", encoding="utf-8"
    )

    found = find_config(tmp_path)
    assert found is not None
    assert found.name == CONFIG_FILENAME


def test_find_config_returns_pyproject_when_table_present(tmp_path: Path) -> None:
    (tmp_path / PYPROJECT_FILENAME).write_text(
        "[tool.m-cli]\n[tool.m-cli.lint]\nrules = 'all'\n", encoding="utf-8"
    )

    found = find_config(tmp_path)
    assert found is not None
    assert found.name == PYPROJECT_FILENAME


def test_find_config_skips_pyproject_without_m_cli_table(tmp_path: Path) -> None:
    """A pyproject.toml without a ``[tool.m-cli]`` section isn't ours."""
    (tmp_path / PYPROJECT_FILENAME).write_text("[tool.ruff]\nline-length = 100\n", encoding="utf-8")

    assert find_config(tmp_path) is None


def test_find_config_stops_at_git_boundary(tmp_path: Path) -> None:
    """Walking should stop at a directory containing ``.git``."""
    project = tmp_path / "proj"
    nested = project / "src"
    nested.mkdir(parents=True)
    (project / ".git").mkdir()
    # Place a config OUTSIDE the git root — find_config must not see it.
    (tmp_path / CONFIG_FILENAME).write_text("[lint]\nrules = 'all'\n", encoding="utf-8")

    assert find_config(nested) is None


def test_find_config_returns_none_when_absent(tmp_path: Path) -> None:
    assert find_config(tmp_path) is None


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


def test_load_config_reads_lint_rules_and_disable(tmp_path: Path) -> None:
    (tmp_path / CONFIG_FILENAME).write_text(
        '[lint]\nrules = "all"\ndisable = ["M-XINDX-013", "M-XINDX-019"]\n',
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.lint_rules == "all"
    assert cfg.lint_disable == ("M-XINDX-013", "M-XINDX-019")


def test_load_config_reads_severity_overrides(tmp_path: Path) -> None:
    (tmp_path / CONFIG_FILENAME).write_text(
        '[lint.severity]\n"M-XINDX-019" = "warning"\n"M-XINDX-013" = "info"\n',
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.lint_severity_overrides == {
        "M-XINDX-019": Severity.WARNING,
        "M-XINDX-013": Severity.INFO,
    }


def test_load_config_reads_fmt_rules(tmp_path: Path) -> None:
    (tmp_path / CONFIG_FILENAME).write_text('[fmt]\nrules = "canonical"\n', encoding="utf-8")

    cfg = load_config(tmp_path)
    assert cfg.fmt_rules == "canonical"


def test_load_config_reads_pyproject_toml(tmp_path: Path) -> None:
    (tmp_path / PYPROJECT_FILENAME).write_text(
        "[tool.m-cli]\n[tool.m-cli.lint]\nrules = 'sac'\n", encoding="utf-8"
    )

    cfg = load_config(tmp_path)
    assert cfg.lint_rules == "sac"


def test_load_config_returns_empty_when_absent(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    assert cfg == Config.empty()


def test_load_config_raises_on_unknown_severity(tmp_path: Path) -> None:
    (tmp_path / CONFIG_FILENAME).write_text(
        '[lint.severity]\n"M-XINDX-019" = "critical"\n', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="unknown severity"):
        load_config(tmp_path)


def test_load_config_raises_on_disable_not_a_list(tmp_path: Path) -> None:
    (tmp_path / CONFIG_FILENAME).write_text('[lint]\ndisable = "M-XINDX-013"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="disable must be a list"):
        load_config(tmp_path)


def test_load_config_ignores_unknown_keys(tmp_path: Path) -> None:
    """Unknown keys must not raise — keeps forward compatibility cheap."""
    (tmp_path / CONFIG_FILENAME).write_text(
        '[lint]\nrules = "xindex"\nfuture_key = "ignored"\n',
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.lint_rules == "xindex"


def test_load_config_records_source_path(tmp_path: Path) -> None:
    cfg_path = tmp_path / CONFIG_FILENAME
    cfg_path.write_text("[lint]\nrules = 'all'\n", encoding="utf-8")

    cfg = load_config(tmp_path)
    assert cfg.source_path == cfg_path


def test_config_empty_returns_clean_defaults() -> None:
    cfg = Config.empty()
    assert cfg.lint_rules is None
    assert cfg.lint_disable == ()
    assert cfg.lint_severity_overrides == {}
    assert cfg.lint_target_engine is None
    assert cfg.fmt_rules is None
    assert cfg.source_path is None


# ---------------------------------------------------------------------------
# target_engine
# ---------------------------------------------------------------------------


def test_load_config_reads_target_engine(tmp_path: Path) -> None:
    cfg_path = tmp_path / CONFIG_FILENAME
    cfg_path.write_text(
        '[lint]\nrules = "default"\ntarget_engine = "yottadb"\n',
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert cfg.lint_target_engine == "yottadb"


def test_load_config_target_engine_is_normalized_lowercase(tmp_path: Path) -> None:
    cfg_path = tmp_path / CONFIG_FILENAME
    cfg_path.write_text(
        '[lint]\ntarget_engine = "  IRIS  "\n',
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert cfg.lint_target_engine == "iris"


def test_load_config_rejects_unknown_target_engine(tmp_path: Path) -> None:
    cfg_path = tmp_path / CONFIG_FILENAME
    cfg_path.write_text(
        '[lint]\ntarget_engine = "gtm"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="target_engine"):
        load_config(tmp_path)


def test_load_config_rejects_non_string_target_engine(tmp_path: Path) -> None:
    cfg_path = tmp_path / CONFIG_FILENAME
    cfg_path.write_text(
        "[lint]\ntarget_engine = 42\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="target_engine.*string"):
        load_config(tmp_path)


def test_load_config_target_engine_omitted_yields_none(tmp_path: Path) -> None:
    cfg_path = tmp_path / CONFIG_FILENAME
    cfg_path.write_text('[lint]\nrules = "default"\n', encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.lint_target_engine is None


# ---------------------------------------------------------------------------
# [lint.thresholds]
# ---------------------------------------------------------------------------


def test_load_config_reads_thresholds(tmp_path: Path) -> None:
    cfg_path = tmp_path / CONFIG_FILENAME
    cfg_path.write_text(
        "[lint.thresholds]\nline_length = 120\nroutine_lines = 2000\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert cfg.lint_thresholds == {"line_length": 120, "routine_lines": 2000}


def test_load_config_thresholds_omitted_yields_empty(tmp_path: Path) -> None:
    cfg_path = tmp_path / CONFIG_FILENAME
    cfg_path.write_text('[lint]\nrules = "default"\n', encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.lint_thresholds == {}


def test_load_config_rejects_unknown_threshold(tmp_path: Path) -> None:
    cfg_path = tmp_path / CONFIG_FILENAME
    cfg_path.write_text(
        "[lint.thresholds]\nline_lenght = 120\n",  # typo
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown threshold"):
        load_config(tmp_path)


def test_load_config_rejects_negative_threshold(tmp_path: Path) -> None:
    cfg_path = tmp_path / CONFIG_FILENAME
    cfg_path.write_text(
        "[lint.thresholds]\nline_length = -1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="positive integer"):
        load_config(tmp_path)


def test_load_config_rejects_thresholds_not_a_table(tmp_path: Path) -> None:
    cfg_path = tmp_path / CONFIG_FILENAME
    cfg_path.write_text(
        '[lint]\nthresholds = "boom"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="thresholds.*must be a table"):
        load_config(tmp_path)
