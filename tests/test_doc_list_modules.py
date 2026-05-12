"""Tests for ``m stdlib list`` — print every module + synopsis.

Handler-level: feed a synthetic manifest via --manifest PATH, assert
the output shape (text + JSON). No live ydb / m-stdlib needed.
"""

from __future__ import annotations

import argparse
import json

import pytest

from m_cli.doc.list_modules import list_command


@pytest.fixture
def synthetic_manifest(tmp_path):
    payload = {
        "stdlib_version": "v0.5.0",
        "modules": {
            "STDJSON": {"synopsis": "RFC 8259 JSON encoder/decoder."},
            "STDCSV": {"synopsis": "RFC-4180 CSV parser/writer."},
            "STDB64": {"synopsis": "Base64 (RFC-4648 §4)."},
            "EMPTY": {},  # no synopsis — make sure the handler doesn't crash
        },
    }
    p = tmp_path / "stdlib-manifest.json"
    p.write_text(json.dumps(payload))
    return p


def _ns(**kw) -> argparse.Namespace:
    base = {"manifest": None, "json": False}
    base.update(kw)
    return argparse.Namespace(**base)


def test_list_command_prints_text_table(synthetic_manifest, capsys):
    rc = list_command(_ns(manifest=str(synthetic_manifest)))
    assert rc == 0
    out = capsys.readouterr().out
    # Header carries the version + module count
    assert "v0.5.0" in out
    assert "4 module(s)" in out
    # Each module name appears with its synopsis (or alone for EMPTY)
    assert "STDJSON" in out and "RFC 8259" in out
    assert "STDCSV" in out and "RFC-4180" in out
    assert "STDB64" in out and "Base64" in out
    assert "EMPTY" in out


def test_list_command_alphabetical(synthetic_manifest, capsys):
    list_command(_ns(manifest=str(synthetic_manifest)))
    out = capsys.readouterr().out
    body = out.split("\n\n", 1)[1] if "\n\n" in out else out
    rows = [line.strip().split()[0] for line in body.splitlines() if line.strip()]
    assert rows == sorted(rows)


def test_list_command_json_mode(synthetic_manifest, capsys):
    rc = list_command(_ns(manifest=str(synthetic_manifest), json=True))
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["stdlib_version"] == "v0.5.0"
    names = [m["name"] for m in payload["modules"]]
    assert names == sorted(names)
    assert {"STDJSON", "STDCSV", "STDB64", "EMPTY"} == set(names)
    # Missing synopsis surfaces as an empty string, not a crash.
    empty_entry = next(m for m in payload["modules"] if m["name"] == "EMPTY")
    assert empty_entry["synopsis"] == ""


def test_list_command_missing_manifest_exits_1(tmp_path, capsys, monkeypatch):
    # Force discovery to find nothing.
    monkeypatch.delenv("M_CLI_MANIFEST", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    rc = list_command(_ns())
    err = capsys.readouterr().err
    assert rc == 1  # DOMAIN_FAILURE per CLI-UX guide §3.7
    assert "could not find" in err.lower()


def test_list_command_malformed_manifest_exits_1(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json")
    rc = list_command(_ns(manifest=str(bad)))
    err = capsys.readouterr().err
    assert rc == 1
    assert "failed to load" in err.lower()
