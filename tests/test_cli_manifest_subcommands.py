"""Tests for ``m search`` / ``m manifest`` / ``m examples`` / ``m errors``.

Implements WB3 + WB4 from m-stdlib's discoverability tracker. All four
commands share the same manifest discovery as ``m doc`` and read the
same JSON shape; their tests use the same in-memory manifest fixture.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from m_cli.doc.errors import errors_command
from m_cli.doc.examples import examples_command
from m_cli.doc.manifest import manifest_command
from m_cli.doc.search import search_command


def _manifest() -> dict:
    return {
        "stdlib_version": "v0.5.0",
        "modules": {
            "STDJSON": {
                "synopsis": "RFC 8259 JSON parser + serialiser.",
                "description": "Pure-M parser, validator, and serialiser.",
                "errors": ["U-STDJSON-PARSE", "U-STDJSON-ENCODE"],
                "labels": {
                    "parse": {
                        "signature": "$$parse^STDJSON(text, root)",
                        "synopsis": "Parse `text` into `root`. Returns 1/0.",
                        "description": "Kills root before population.",
                        "examples": ['do  set rc=$$parse^STDJSON("[1,2,3]",.t)'],
                        "raises": [
                            {"code": "U-STDJSON-PARSE", "doc": "malformed input"}
                        ],
                    },
                    "encode": {
                        "signature": "$$encode^STDJSON(node)",
                        "synopsis": "Serialise `node` to JSON text.",
                        "description": "Object members in M collation.",
                        "examples": ["write $$encode^STDJSON(.t)"],
                        "raises": [
                            {"code": "U-STDJSON-ENCODE", "doc": "gappy array"}
                        ],
                    },
                },
            },
            "STDURL": {
                "synopsis": "RFC 3986 URI parser, builder, encoder, resolver.",
                "description": "Seven public extrinsics.",
                "errors": [],
                "labels": {
                    "encode": {
                        "signature": "$$encode^STDURL(s, safe)",
                        "synopsis": "Percent-encode s.",
                        "description": "Unreserved set is ALPHA / DIGIT.",
                        "examples": ['write $$encode^STDURL("hello world","")'],
                        "raises": [],
                    },
                },
            },
            "STDFMT": {
                "synopsis": "Printf-style formatter.",
                "description": "",
                "errors": ["U-STDFMT-MISSING-ARG"],
                "labels": {
                    "f": {
                        "signature": "$$f^STDFMT(template, ...)",
                        "synopsis": "Positional formatter.",
                        "description": "",
                        "examples": [],
                        "raises": [
                            {"code": "U-STDFMT-MISSING-ARG", "doc": "no value at position"}
                        ],
                    },
                },
            },
        },
        "errors": {},
    }


@pytest.fixture
def manifest_path(tmp_path: Path) -> Path:
    p = tmp_path / "stdlib-manifest.json"
    p.write_text(json.dumps(_manifest()))
    return p


def _ns(**kw) -> argparse.Namespace:
    return argparse.Namespace(**kw)


# =============================================================================
# m search
# =============================================================================


class TestSearch:
    def test_finds_synopsis_match(self, manifest_path, capsys):
        # Single token that appears in label synopses → expect hits
        # in synopsis tier (the highest-priority tier).
        rc = search_command(_ns(query="parse", manifest=str(manifest_path), limit=50))
        assert rc == 0
        out = capsys.readouterr().out
        assert "STDJSON.parse" in out

    def test_and_match_excludes_partial_hits(self, manifest_path, capsys):
        # "JSON parser" — both tokens needed. The label haystacks for
        # STDJSON.parse / STDJSON.encode contain "JSON" (via the
        # @example "$$parse^STDJSON...") but not "parser". The
        # AND-match fails; expect zero matches and exit 1.
        rc = search_command(
            _ns(query="JSON parser", manifest=str(manifest_path), limit=50)
        )
        assert rc == 1
        err = capsys.readouterr().err
        assert "no matches" in err.lower()

    def test_url_encode_finds_stdurl_encode(self, manifest_path, capsys):
        rc = search_command(_ns(query="URL encode", manifest=str(manifest_path), limit=50))
        assert rc == 0
        out = capsys.readouterr().out
        assert "STDURL.encode" in out
        # STDJSON.encode's haystack has "encode" but no "URL", so
        # the AND-match on "URL encode" should EXCLUDE it.
        assert "STDJSON.encode" not in out

    def test_no_match_returns_one(self, manifest_path, capsys):
        rc = search_command(
            _ns(query="nopatternmatchesthis", manifest=str(manifest_path), limit=50)
        )
        err = capsys.readouterr().err
        assert rc == 1
        assert "no matches" in err.lower()

    def test_empty_query_returns_two(self, manifest_path, capsys):
        rc = search_command(_ns(query="", manifest=str(manifest_path), limit=50))
        err = capsys.readouterr().err
        assert rc == 2
        assert "missing query" in err.lower()

    def test_case_insensitive(self, manifest_path, capsys):
        rc = search_command(_ns(query="json", manifest=str(manifest_path), limit=50))
        assert rc == 0
        out = capsys.readouterr().out
        assert "STDJSON" in out

    def test_limit_truncates(self, manifest_path, capsys):
        # "encode" matches both STDJSON.encode and STDURL.encode (2 hits).
        # Limit of 1 should truncate to 1.
        rc = search_command(_ns(query="encode", manifest=str(manifest_path), limit=1))
        assert rc == 0
        out_lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
        assert len(out_lines) == 1


# =============================================================================
# m manifest
# =============================================================================


class TestManifest:
    def test_no_path_emits_full_manifest(self, manifest_path, capsys):
        rc = manifest_command(_ns(path="", manifest=str(manifest_path)))
        assert rc == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["stdlib_version"] == "v0.5.0"
        assert "STDJSON" in parsed["modules"]

    def test_module_subpath(self, manifest_path, capsys):
        rc = manifest_command(_ns(path="STDJSON", manifest=str(manifest_path)))
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert "labels" in parsed
        assert "parse" in parsed["labels"]

    def test_module_dot_label_subpath(self, manifest_path, capsys):
        rc = manifest_command(_ns(path="STDJSON.parse", manifest=str(manifest_path)))
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["signature"] == "$$parse^STDJSON(text, root)"

    def test_top_level_key_subpath(self, manifest_path, capsys):
        rc = manifest_command(_ns(path="stdlib_version", manifest=str(manifest_path)))
        assert rc == 0
        out = capsys.readouterr().out
        # JSON-encoded scalar: "v0.5.0"
        assert json.loads(out) == "v0.5.0"

    def test_unknown_path_returns_one(self, manifest_path, capsys):
        rc = manifest_command(_ns(path="STDDOESNOTEXIST", manifest=str(manifest_path)))
        err = capsys.readouterr().err
        assert rc == 1
        assert "not found" in err.lower()

    def test_unknown_label_returns_one(self, manifest_path, capsys):
        rc = manifest_command(_ns(path="STDJSON.nonsuch", manifest=str(manifest_path)))
        err = capsys.readouterr().err
        assert rc == 1
        assert "not found" in err.lower()


# =============================================================================
# m examples
# =============================================================================


class TestExamples:
    def test_no_module_walks_all(self, manifest_path, capsys):
        rc = examples_command(_ns(module="", manifest=str(manifest_path)))
        assert rc == 0
        out = capsys.readouterr().out
        # Three labels have examples in the fixture: STDJSON.parse,
        # STDJSON.encode, STDURL.encode. STDFMT.f has no examples.
        assert "STDJSON.parse:" in out
        assert "STDJSON.encode:" in out
        assert "STDURL.encode:" in out
        assert "STDFMT.f:" not in out

    def test_module_filter(self, manifest_path, capsys):
        rc = examples_command(_ns(module="STDJSON", manifest=str(manifest_path)))
        assert rc == 0
        out = capsys.readouterr().out
        assert "STDJSON.parse:" in out
        assert "STDJSON.encode:" in out
        assert "STDURL" not in out

    def test_unknown_module_returns_one(self, manifest_path, capsys):
        rc = examples_command(_ns(module="STDDOESNOTEXIST", manifest=str(manifest_path)))
        err = capsys.readouterr().err
        assert rc == 1
        assert "not found" in err.lower()

    def test_module_with_no_examples_returns_one(self, manifest_path, capsys):
        rc = examples_command(_ns(module="STDFMT", manifest=str(manifest_path)))
        err = capsys.readouterr().err
        assert rc == 1
        assert "no examples" in err.lower()


# =============================================================================
# m errors
# =============================================================================


class TestErrors:
    def test_lists_every_code_from_manifest(self, manifest_path, capsys):
        rc = errors_command(_ns(json=False, manifest=str(manifest_path)))
        assert rc == 0
        out = capsys.readouterr().out
        assert "U-STDJSON-PARSE" in out
        assert "U-STDJSON-ENCODE" in out
        assert "U-STDFMT-MISSING-ARG" in out

    def test_associates_codes_with_modules_and_labels(self, manifest_path, capsys):
        rc = errors_command(_ns(json=False, manifest=str(manifest_path)))
        assert rc == 0
        out = capsys.readouterr().out
        # U-STDJSON-PARSE comes from STDJSON.parse
        for line in out.splitlines():
            if "U-STDJSON-PARSE" in line:
                assert "STDJSON" in line
                assert "parse" in line
                break
        else:
            pytest.fail("U-STDJSON-PARSE not found in output")

    def test_json_flag(self, manifest_path, capsys):
        rc = errors_command(_ns(json=True, manifest=str(manifest_path)))
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert "U-STDJSON-PARSE" in parsed
        assert parsed["U-STDJSON-PARSE"]["module"] == "STDJSON"
        assert "parse" in parsed["U-STDJSON-PARSE"]["labels"]

    def test_prefers_sidecar_when_available(self, tmp_path, capsys):
        # Create both a main manifest with NO raises and a sidecar
        # with codes — the sidecar should win.
        m = {
            "stdlib_version": "v0.5.0",
            "modules": {"STDJSON": {"synopsis": "x", "labels": {"parse": {"raises": []}}}},
        }
        (tmp_path / "stdlib-manifest.json").write_text(json.dumps(m))
        sidecar = {
            "U-STDX-FROM-SIDECAR": {"module": "STDX", "labels": ["fromSidecar"]},
        }
        (tmp_path / "errors.json").write_text(json.dumps(sidecar))
        rc = errors_command(_ns(json=False, manifest=str(tmp_path / "stdlib-manifest.json")))
        out = capsys.readouterr().out
        assert rc == 0
        assert "U-STDX-FROM-SIDECAR" in out

    def test_empty_manifest_returns_one(self, tmp_path, capsys):
        m = {"stdlib_version": "v0", "modules": {}}
        p = tmp_path / "stdlib-manifest.json"
        p.write_text(json.dumps(m))
        rc = errors_command(_ns(json=False, manifest=str(p)))
        err = capsys.readouterr().err
        assert rc == 1
        assert "no u-std" in err.lower()


# =============================================================================
# Manifest-resolution failures (shared across all four commands)
# =============================================================================


class TestManifestErrors:
    def test_missing_manifest_returns_one(self, tmp_path, capsys, monkeypatch):
        # Domain failure per CLI-UX §3.7 (was: usage error / exit 2).
        monkeypatch.delenv("M_CLI_MANIFEST", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        for cmd, kwargs in [
            (search_command, {"query": "x", "limit": 50}),
            (manifest_command, {"path": ""}),
            (examples_command, {"module": ""}),
            (errors_command, {"json": False}),
        ]:
            rc = cmd(_ns(manifest=None, **kwargs))
            assert rc == 1, f"{cmd.__name__}: domain failure exit 1 when manifest unreachable"

    def test_malformed_manifest_returns_one(self, tmp_path, capsys):
        # Domain failure per CLI-UX §3.7 (was: usage error / exit 2).
        bad = tmp_path / "bad.json"
        bad.write_text("{ not json")
        for cmd, kwargs in [
            (search_command, {"query": "x", "limit": 50}),
            (manifest_command, {"path": ""}),
            (examples_command, {"module": ""}),
            (errors_command, {"json": False}),
        ]:
            rc = cmd(_ns(manifest=str(bad), **kwargs))
            assert rc == 1, f"{cmd.__name__} should return 1 (domain failure) on malformed manifest"
