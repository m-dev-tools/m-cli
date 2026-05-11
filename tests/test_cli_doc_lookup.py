"""Tests for ``m doc`` — godoc-style symbol lookup over the m-stdlib manifest.

Implements WB1 from m-stdlib's discoverability tracker. Covers the
three layers:

* :mod:`m_cli.doc.lookup`   — manifest discovery + symbol resolution
* :mod:`m_cli.doc.format`   — long/short/JSON output formatters
* :mod:`m_cli.doc.cli`      — argparse handler that ties them together

Tests pass an in-memory manifest fixture so they don't depend on
m-stdlib being installed alongside.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from m_cli.doc.cli import doc_command
from m_cli.doc.format import (
    format_label_json,
    format_label_list,
    format_label_long,
    format_label_short,
    format_module_long,
    format_module_short,
)
from m_cli.doc.lookup import (
    LabelMatch,
    ModuleMatch,
    find_manifest,
    list_modules,
    resolve_symbol,
)

# ----- fixtures --------------------------------------------------------------


def _manifest() -> dict:
    """Minimal but realistic manifest fixture matching the schema in
    m-stdlib/tools/gen-manifest.py."""
    return {
        "stdlib_version": "v0.5.0",
        "modules": {
            "STDJSON": {
                "synopsis": "RFC 8259 JSON parser + serialiser.",
                "description": "Pure-M parser, validator, and serialiser.",
                "errors": ["U-STDJSON-PARSE", "U-STDJSON-ENCODE"],
                "labels": {
                    "parse": {
                        "form": "extrinsic",
                        "signature": "$$parse^STDJSON(text, root)",
                        "synopsis": "Parse `text` into `root`. Returns 1/0.",
                        "params": [
                            {"name": "text", "type": "string", "doc": "RFC-8259 JSON document"},
                            {"name": "root", "type": "array", "doc": "caller-owned destination"},
                        ],
                        "returns": {"type": "bool", "doc": "1 on success; 0 on parse failure"},
                        "raises": [
                            {"code": "U-STDJSON-PARSE", "doc": "malformed input"}
                        ],
                        "examples": ['do  set rc=$$parse^STDJSON("[1,2,3]",.t)'],
                        "since": "v0.2.0",
                        "stable": "stable",
                        "see_also": ["$$valid^STDJSON", "$$lastError^STDJSON"],
                        "description": "Kills `root` first.",
                        "source": {"file": "src/STDJSON.m", "line": 39},
                    },
                    "valid": {
                        "form": "extrinsic",
                        "signature": "$$valid^STDJSON(text)",
                        "synopsis": "True iff `text` is conformant RFC-8259 JSON.",
                        "params": [{"name": "text", "type": "string", "doc": "candidate"}],
                        "returns": {"type": "bool", "doc": "1 iff conformant"},
                        "raises": [],
                        "examples": [],
                        "since": "v0.2.0",
                        "stable": "stable",
                        "see_also": [],
                        "description": "",
                        "source": {"file": "src/STDJSON.m", "line": 60},
                    },
                },
                "source": {"file": "src/STDJSON.m", "line": 1},
            },
            "STDB64": {
                "synopsis": "RFC-4648 Base64 (standard + URL-safe).",
                "description": "",
                "errors": [],
                "labels": {
                    "parse": {
                        # A second `parse` so fuzzy lookup has something to disambiguate.
                        "form": "extrinsic",
                        "signature": "$$parse^STDB64(text)",
                        "synopsis": "(non-existent in real STDB64; fuzzy-test fixture only)",
                        "params": [],
                        "returns": {"type": "string", "doc": ""},
                        "raises": [],
                        "examples": [],
                        "since": "v0.0.2",
                        "stable": "experimental",
                        "see_also": [],
                        "description": "",
                        "source": {"file": "src/STDB64.m", "line": 99},
                    },
                    "encode": {
                        "form": "extrinsic",
                        "signature": "$$encode^STDB64(data)",
                        "synopsis": "Standard base64 (RFC-4648 §4) with padding.",
                        "params": [{"name": "data", "type": "string", "doc": "byte string"}],
                        "returns": {"type": "string", "doc": "base64"},
                        "raises": [],
                        "examples": ['write $$encode^STDB64("foo")'],
                        "since": "v0.0.2",
                        "stable": "stable",
                        "see_also": [],
                        "description": "",
                        "source": {"file": "src/STDB64.m", "line": 25},
                    },
                },
                "source": {"file": "src/STDB64.m", "line": 1},
            },
        },
        "errors": {},
    }


def _ns(**kw) -> argparse.Namespace:
    base = {
        "symbol": "",
        "short": False,
        "json": False,
        "manifest": None,
    }
    base.update(kw)
    return argparse.Namespace(**base)


# =============================================================================
# lookup.py
# =============================================================================


class TestResolveSymbol:
    def test_module_overview(self):
        modules, labels = resolve_symbol("STDJSON", _manifest())
        assert len(modules) == 1
        assert modules[0].module == "STDJSON"
        assert labels == []

    def test_unknown_module_returns_empty(self):
        modules, labels = resolve_symbol("STDDOESNOTEXIST", _manifest())
        assert modules == []
        assert labels == []

    def test_dotted_single_label(self):
        modules, labels = resolve_symbol("STDJSON.parse", _manifest())
        assert modules == []
        assert len(labels) == 1
        assert labels[0].module == "STDJSON"
        assert labels[0].label == "parse"

    def test_dotted_unknown_label_returns_empty(self):
        modules, labels = resolve_symbol("STDJSON.nonsuch", _manifest())
        assert modules == []
        assert labels == []

    def test_fuzzy_bare_name_finds_all_matches(self):
        modules, labels = resolve_symbol("parse", _manifest())
        assert modules == []
        assert {(x.module, x.label) for x in labels} == {
            ("STDB64", "parse"),
            ("STDJSON", "parse"),
        }

    def test_fuzzy_bare_name_unique_returns_one(self):
        modules, labels = resolve_symbol("encode", _manifest())
        assert modules == []
        assert len(labels) == 1
        assert labels[0].module == "STDB64" and labels[0].label == "encode"

    def test_empty_symbol_returns_empty(self):
        modules, labels = resolve_symbol("", _manifest())
        assert modules == [] and labels == []


class TestListModules:
    def test_returns_sorted_list(self):
        assert list_modules(_manifest()) == ["STDB64", "STDJSON"]


# =============================================================================
# find_manifest discovery order
# =============================================================================


class TestFindManifest:
    def test_explicit_path_wins_when_exists(self, tmp_path):
        p = tmp_path / "m.json"
        p.write_text("{}")
        assert find_manifest(explicit=str(p)) == p

    def test_explicit_missing_returns_none(self, tmp_path):
        assert find_manifest(explicit=str(tmp_path / "nope.json")) is None

    def test_walks_up_from_cwd(self, tmp_path):
        # Set up tmp_path/dist/stdlib-manifest.json and start search
        # from a deeper subdir.
        dist = tmp_path / "dist"
        dist.mkdir()
        target = dist / "stdlib-manifest.json"
        target.write_text("{}")
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        result = find_manifest(start=deep, env={})
        assert result == target

    def test_env_var_overrides_walk(self, tmp_path):
        target = tmp_path / "alt.json"
        target.write_text("{}")
        result = find_manifest(env={"M_CLI_MANIFEST": str(target)}, start=Path("/"))
        assert result == target


# =============================================================================
# format.py
# =============================================================================


class TestFormatModuleLong:
    def test_includes_synopsis_and_label_list(self):
        manifest = _manifest()
        m = ModuleMatch(module="STDJSON", module_data=manifest["modules"]["STDJSON"])
        out = format_module_long(m)
        assert "module STDJSON" in out
        assert "RFC 8259 JSON parser + serialiser." in out
        assert "parse" in out
        assert "valid" in out
        assert "U-STDJSON-PARSE" in out
        assert "src/STDJSON.m" in out


class TestFormatLabelLong:
    def test_includes_signature_synopsis_params_returns_raises_example_source(self):
        manifest = _manifest()
        match = LabelMatch(
            module="STDJSON",
            label="parse",
            label_data=manifest["modules"]["STDJSON"]["labels"]["parse"],
        )
        out = format_label_long(match)
        assert "$$parse^STDJSON(text, root)" in out
        assert "→ bool" in out
        assert "Parse `text` into `root`" in out
        assert "text" in out and "RFC-8259" in out
        assert "returns:" in out
        assert "raises:" in out and "U-STDJSON-PARSE" in out
        assert "since: v0.2.0" in out
        assert "stable" in out
        assert "see:" in out and "$$valid^STDJSON" in out
        assert "example:" in out
        assert "src/STDJSON.m:39" in out


class TestFormatShort:
    def test_module_short_is_one_line(self):
        manifest = _manifest()
        m = ModuleMatch(module="STDJSON", module_data=manifest["modules"]["STDJSON"])
        out = format_module_short(m)
        assert out.count("\n") == 1
        assert "STDJSON" in out and "RFC 8259" in out

    def test_label_short_is_one_line(self):
        manifest = _manifest()
        match = LabelMatch(
            module="STDJSON",
            label="parse",
            label_data=manifest["modules"]["STDJSON"]["labels"]["parse"],
        )
        out = format_label_short(match)
        assert out.count("\n") == 1
        assert "STDJSON.parse" in out


class TestFormatJson:
    def test_label_json_round_trips(self):
        manifest = _manifest()
        match = LabelMatch(
            module="STDJSON",
            label="parse",
            label_data=manifest["modules"]["STDJSON"]["labels"]["parse"],
        )
        out = format_label_json(match)
        parsed = json.loads(out)
        assert parsed["signature"] == "$$parse^STDJSON(text, root)"


class TestFormatLabelList:
    def test_lists_qualified_names(self):
        manifest = _manifest()
        matches = [
            LabelMatch("STDB64", "parse", manifest["modules"]["STDB64"]["labels"]["parse"]),
            LabelMatch("STDJSON", "parse", manifest["modules"]["STDJSON"]["labels"]["parse"]),
        ]
        out = format_label_list(matches)
        assert "2 matches:" in out
        assert "STDB64.parse" in out
        assert "STDJSON.parse" in out


# =============================================================================
# cli.py — doc_command behaviour (with manifest fixture on disk)
# =============================================================================


@pytest.fixture
def manifest_path(tmp_path: Path) -> Path:
    p = tmp_path / "stdlib-manifest.json"
    p.write_text(json.dumps(_manifest()))
    return p


class TestDocCommandLong:
    def test_module_long(self, manifest_path, capsys):
        rc = doc_command(_ns(symbol="STDJSON", manifest=str(manifest_path)))
        out = capsys.readouterr().out
        assert rc == 0
        assert "module STDJSON" in out
        assert "parse" in out

    def test_label_long(self, manifest_path, capsys):
        rc = doc_command(_ns(symbol="STDJSON.parse", manifest=str(manifest_path)))
        out = capsys.readouterr().out
        assert rc == 0
        assert "$$parse^STDJSON" in out
        assert "src/STDJSON.m:39" in out

    def test_no_symbol_lists_modules(self, manifest_path, capsys):
        rc = doc_command(_ns(manifest=str(manifest_path)))
        out = capsys.readouterr().out
        assert rc == 0
        assert "m-stdlib v0.5.0" in out
        assert "STDJSON" in out and "STDB64" in out

    def test_unknown_symbol_returns_one(self, manifest_path, capsys):
        rc = doc_command(_ns(symbol="STDDOESNOTEXIST", manifest=str(manifest_path)))
        err = capsys.readouterr().err
        assert rc == 1
        assert "no match" in err.lower()


class TestDocCommandShort:
    def test_short_label(self, manifest_path, capsys):
        rc = doc_command(
            _ns(symbol="STDJSON.parse", short=True, manifest=str(manifest_path))
        )
        out = capsys.readouterr().out
        assert rc == 0
        # Short = one line.
        assert out.count("\n") == 1
        assert "STDJSON.parse" in out


class TestDocCommandJson:
    def test_json_label(self, manifest_path, capsys):
        rc = doc_command(
            _ns(symbol="STDJSON.parse", json=True, manifest=str(manifest_path))
        )
        out = capsys.readouterr().out
        assert rc == 0
        parsed = json.loads(out)
        assert parsed["signature"] == "$$parse^STDJSON(text, root)"

    def test_json_module(self, manifest_path, capsys):
        rc = doc_command(_ns(symbol="STDJSON", json=True, manifest=str(manifest_path)))
        out = capsys.readouterr().out
        assert rc == 0
        parsed = json.loads(out)
        assert "labels" in parsed
        assert "parse" in parsed["labels"]

    def test_json_fuzzy_returns_array(self, manifest_path, capsys):
        rc = doc_command(_ns(symbol="parse", json=True, manifest=str(manifest_path)))
        out = capsys.readouterr().out
        assert rc == 0
        parsed = json.loads(out)
        assert isinstance(parsed, list)
        assert {p["module"] for p in parsed} == {"STDJSON", "STDB64"}


class TestDocCommandFuzzy:
    def test_multi_hit_lists_candidates(self, manifest_path, capsys):
        rc = doc_command(_ns(symbol="parse", manifest=str(manifest_path)))
        out = capsys.readouterr().out
        assert rc == 0
        assert "2 matches:" in out
        assert "STDJSON.parse" in out and "STDB64.parse" in out

    def test_unique_hit_renders_long(self, manifest_path, capsys):
        rc = doc_command(_ns(symbol="encode", manifest=str(manifest_path)))
        out = capsys.readouterr().out
        assert rc == 0
        assert "$$encode^STDB64" in out


class TestDocCommandManifestErrors:
    def test_missing_manifest_returns_one(self, tmp_path, capsys, monkeypatch):
        # Domain failure per CLI-UX §3.7 (was: usage error / exit 2).
        # Force discovery to find nothing: no walk-up hit, no env var,
        # no fallback file (stub HOME).
        monkeypatch.delenv("M_CLI_MANIFEST", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        rc = doc_command(_ns(symbol="STDJSON"))
        err = capsys.readouterr().err
        assert rc == 1
        assert "could not find" in err.lower()

    def test_malformed_manifest_returns_one(self, tmp_path, capsys):
        # Domain failure per CLI-UX §3.7.
        bad = tmp_path / "bad.json"
        bad.write_text("{ this is not json")
        rc = doc_command(_ns(symbol="STDJSON", manifest=str(bad)))
        err = capsys.readouterr().err
        assert rc == 1
        assert "failed to load" in err.lower()
