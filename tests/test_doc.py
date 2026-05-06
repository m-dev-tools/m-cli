"""Tests for ``m doc`` — extract M docstrings to Markdown / HTML."""

from __future__ import annotations

import argparse
from pathlib import Path

from m_cli.doc import doc_command
from m_cli.doc.extract import (
    LabelDoc,
    RoutineDoc,
    extract_routine_doc,
)
from m_cli.doc.render import render_html, render_markdown

# ----------------------------------------------------------------- extraction


def test_extract_routine_doc_carries_routine_name():
    src = b"HELLO ; @summary  HELLO -- demo greeting\n quit\n"
    rd = extract_routine_doc(Path("HELLO.m"), src)
    assert rd.name == "HELLO"


def test_extract_routine_doc_pulls_summary():
    src = b"HELLO ; @summary  HELLO -- demo greeting\n quit\n"
    rd = extract_routine_doc(Path("HELLO.m"), src)
    assert rd.summary == "HELLO -- demo greeting"


def test_extract_routine_doc_handles_no_summary():
    src = b"HELLO ;\n quit\n"
    rd = extract_routine_doc(Path("HELLO.m"), src)
    assert rd.summary == ""


def test_extract_routine_doc_pulls_version_stub():
    src = (
        b"HELLO ; @summary  greeting\n"
        b" ;;1.0;HELLO WORLD;;0;Build 1\n"
        b" quit\n"
    )
    rd = extract_routine_doc(Path("HELLO.m"), src)
    assert rd.version == "1.0"
    assert rd.package == "HELLO WORLD"


def test_extract_routine_doc_no_version_stub():
    src = b"HELLO ; @summary  greeting\n quit\n"
    rd = extract_routine_doc(Path("HELLO.m"), src)
    assert rd.version == ""
    assert rd.package == ""


def test_extract_routine_doc_collects_labels():
    src = (
        b"HELLO ; @summary  greeting\n"
        b" quit\n"
        b" ;\n"
        b"greet(name) ; @summary  $$greet(name) -> friendly greeting\n"
        b' quit "Hello, "_name_"!"\n'
        b' ;\n'
        b'shout(name) ; @summary  uppercase greeting\n'
        b' quit $zconvert($$greet(name),"U")\n'
    )
    rd = extract_routine_doc(Path("HELLO.m"), src)
    names = [lbl.name for lbl in rd.labels]
    assert "greet" in names
    assert "shout" in names


def test_extract_routine_doc_label_carries_formals():
    src = (
        b"HELLO ; @summary  greeting\n"
        b" quit\n"
        b" ;\n"
        b"greet(name) ; @summary  greet\n"
        b' quit "Hello, "_name_"!"\n'
    )
    rd = extract_routine_doc(Path("HELLO.m"), src)
    greet = next(lbl for lbl in rd.labels if lbl.name == "greet")
    assert greet.formals == "(name)"


def test_extract_routine_doc_label_carries_summary():
    src = (
        b"HELLO ; @summary  greeting\n"
        b" quit\n"
        b" ;\n"
        b"greet(name) ; @summary  $$greet(name) returns a hello string\n"
        b' quit "Hello, "_name_"!"\n'
    )
    rd = extract_routine_doc(Path("HELLO.m"), src)
    greet = next(lbl for lbl in rd.labels if lbl.name == "greet")
    assert "returns a hello string" in greet.summary


# -------------------------------------------------------------- markdown output


def test_render_markdown_emits_routine_heading():
    rd = RoutineDoc(
        path=Path("HELLO.m"),
        name="HELLO",
        summary="greeting",
        version="1.0",
        package="HELLO WORLD",
        labels=[],
    )
    md = render_markdown([rd])
    assert "## HELLO" in md
    assert "greeting" in md
    assert "1.0" in md or "HELLO WORLD" in md


def test_render_markdown_emits_label_section():
    rd = RoutineDoc(
        path=Path("HELLO.m"),
        name="HELLO",
        summary="",
        version="",
        package="",
        labels=[
            LabelDoc(name="greet", formals="(name)", summary="returns hello"),
        ],
    )
    md = render_markdown([rd])
    assert "greet" in md
    assert "(name)" in md
    assert "returns hello" in md


def test_render_markdown_handles_multiple_routines():
    rd1 = RoutineDoc(path=Path("A.m"), name="A", summary="", version="", package="", labels=[])
    rd2 = RoutineDoc(path=Path("B.m"), name="B", summary="", version="", package="", labels=[])
    md = render_markdown([rd1, rd2])
    assert "## A" in md
    assert "## B" in md


# ------------------------------------------------------------------ html output


def test_render_html_wraps_in_html_tags():
    rd = RoutineDoc(
        path=Path("HELLO.m"),
        name="HELLO",
        summary="greeting",
        version="",
        package="",
        labels=[],
    )
    html = render_html([rd])
    assert "<html" in html.lower()
    assert "<body" in html.lower()
    assert "HELLO" in html


# ----------------------------------------------------------------- doc_command


def _ns(**kw) -> argparse.Namespace:
    base = {"paths": [], "format": "markdown", "output": None}
    base.update(kw)
    return argparse.Namespace(**base)


def test_doc_command_writes_stdout_by_default(tmp_path, capsys):
    f = tmp_path / "HELLO.m"
    f.write_text("HELLO ; @summary  greeting\n quit\n")
    rc = doc_command(_ns(paths=[tmp_path]))
    out = capsys.readouterr().out
    assert rc == 0
    assert "## HELLO" in out


def test_doc_command_writes_output_file(tmp_path):
    f = tmp_path / "HELLO.m"
    f.write_text("HELLO ; @summary  greeting\n quit\n")
    out_path = tmp_path / "DOCS.md"
    rc = doc_command(_ns(paths=[tmp_path], output=out_path))
    assert rc == 0
    body = out_path.read_text()
    assert "## HELLO" in body


def test_doc_command_no_files_returns_two(tmp_path, capsys):
    rc = doc_command(_ns(paths=[tmp_path]))
    err = capsys.readouterr().err
    assert rc == 2
    assert "no .m files" in err.lower() or "no m files" in err.lower()


def test_doc_command_html_format(tmp_path, capsys):
    f = tmp_path / "HELLO.m"
    f.write_text("HELLO ; @summary  greeting\n quit\n")
    rc = doc_command(_ns(paths=[tmp_path], format="html"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "<html" in out.lower()
