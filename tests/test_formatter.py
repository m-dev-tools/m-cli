"""Identity-formatter round-trip tests.

The Step 1 formatter is the identity pass: parse → tree.text → bytes.
For any cleanly-parsing M source, the formatted output must equal the
input byte-for-byte.

These tests are the floor: nothing else in m fmt is meaningful unless
the round-trip holds on real-world M code.
"""

from __future__ import annotations

import pytest

from m_cli.fmt.formatter import ParseError, format_source

# ---------------------------------------------------------------------------
# Hand-crafted MUMPS samples (each must round-trip identically)
# ---------------------------------------------------------------------------

SAMPLES = {
    "minimal": b"hello ;the simplest routine\n quit\n",
    "label_with_args": (b"add(a,b) ;adder\n new sum\n set sum=a+b\n quit sum\n"),
    "dot_block": (b"loop ;trivial dot block\n new i\n for i=1:1:5 do\n . write i,!\n quit\n"),
    "global_set": (b"setpat(id,name) ;set patient name\n set ^DPT(id,0)=name\n quit\n"),
    "comment_only": b";; package metadata\n;;5.1;Routines;;Jan 23, 1996\n",
    "multiline_string": (b'msg ;message\n write "line one",!\n write "line two",!\n quit\n'),
    "naked_reference": (b'naked ;naked references\n set ^DPT(1,0)="a"\n set ^(1)="b"\n quit\n'),
}


@pytest.mark.parametrize("name,src", list(SAMPLES.items()))
def test_round_trip_identity(name: str, src: bytes) -> None:
    """Every clean sample must round-trip byte-for-byte."""
    out = format_source(src)
    assert out == src, f"sample {name!r} did not round-trip"


def test_idempotent() -> None:
    """fmt(fmt(x)) == fmt(x) for every sample."""
    for name, src in SAMPLES.items():
        once = format_source(src)
        twice = format_source(once)
        assert once == twice, f"sample {name!r} not idempotent"


def test_parse_error_is_raised() -> None:
    """Source with a bad line should raise ParseError, not silently rewrite."""
    bad = b"this is not a valid M routine at all !@#$%\n"
    with pytest.raises(ParseError):
        format_source(bad)


def test_type_error_on_str() -> None:
    """The API takes bytes, not str — confirm we reject str up front."""
    with pytest.raises(TypeError):
        format_source("hello\n")  # type: ignore[arg-type]


def test_empty_file() -> None:
    """An empty file is trivially clean."""
    assert format_source(b"") == b""
