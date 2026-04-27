"""Tests for `m test` discovery — finding test suites and labels via tree-sitter."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from m_cli.test.discovery import (
    TestCase,
    TestSuite,
    discover,
    find_test_cases,
    is_suite_file,
)

# ---------------------------------------------------------------------------
# is_suite_file
# ---------------------------------------------------------------------------


def test_suite_file_recognised_by_TST_suffix(tmp_path: Path) -> None:
    p = tmp_path / "HELLOTST.m"
    p.write_text("HELLOTST\n quit\n")
    assert is_suite_file(p) is True


def test_non_TST_file_is_not_a_suite(tmp_path: Path) -> None:
    p = tmp_path / "HELLO.m"
    p.write_text("HELLO\n quit\n")
    assert is_suite_file(p) is False


def test_lowercase_tst_is_not_a_suite(tmp_path: Path) -> None:
    # VistA convention is uppercase. Be strict.
    p = tmp_path / "hellotst.m"
    p.write_text("hellotst\n quit\n")
    assert is_suite_file(p) is False


def test_non_m_file_is_not_a_suite(tmp_path: Path) -> None:
    p = tmp_path / "HELLOTST.txt"
    p.write_text("not M source")
    assert is_suite_file(p) is False


# ---------------------------------------------------------------------------
# find_test_cases
# ---------------------------------------------------------------------------


HELLOTST_SRC = dedent("""\
    HELLOTST ; Test suite for hello.m
            new pass,fail
            do start^TESTRUN(.pass,.fail)
            do tGreetWorld(.pass,.fail)
            do tGreetName(.pass,.fail)
            do report^TESTRUN(pass,fail)
            quit
            ;
    tGreetWorld(pass,fail)  ;@TEST "greet() returns Hello, World!"
            do eq^TESTRUN(.pass,.fail,"x","x","trivial")
            quit
            ;
    tGreetName(pass,fail)
            do eq^TESTRUN(.pass,.fail,"y","y","trivial")
            quit
""").encode("ascii")


def test_find_two_test_labels() -> None:
    cases = find_test_cases(Path("HELLOTST.m"), HELLOTST_SRC)
    assert len(cases) == 2
    labels = [c.label for c in cases]
    assert labels == ["tGreetWorld", "tGreetName"]


def test_test_case_carries_suite_name() -> None:
    cases = find_test_cases(Path("/path/to/HELLOTST.m"), HELLOTST_SRC)
    for c in cases:
        assert c.suite == "HELLOTST"


def test_test_case_extracts_TEST_description() -> None:
    cases = find_test_cases(Path("HELLOTST.m"), HELLOTST_SRC)
    by_label = {c.label: c for c in cases}
    assert by_label["tGreetWorld"].description == "greet() returns Hello, World!"
    assert by_label["tGreetName"].description is None


def test_test_case_records_line_number() -> None:
    cases = find_test_cases(Path("HELLOTST.m"), HELLOTST_SRC)
    # tGreetWorld is on line 9 of the source above (1-indexed)
    by_label = {c.label: c for c in cases}
    assert by_label["tGreetWorld"].line == 9


def test_label_without_pass_fail_formals_is_not_a_test() -> None:
    src = dedent("""\
        HELLOTST
                quit
                ;
        helper(x,y)
                quit 1
                ;
        tValid(pass,fail)
                quit
    """).encode("ascii")
    cases = find_test_cases(Path("HELLOTST.m"), src)
    labels = [c.label for c in cases]
    assert labels == ["tValid"]


def test_label_starting_with_lowercase_t_but_not_followed_by_uppercase_skipped() -> None:
    # `tools(pass,fail)` doesn't follow the `t<UpperCase>` convention.
    src = dedent("""\
        HELLOTST
                quit
                ;
        tools(pass,fail)
                quit
                ;
        tValid(pass,fail)
                quit
    """).encode("ascii")
    cases = find_test_cases(Path("HELLOTST.m"), src)
    labels = [c.label for c in cases]
    assert labels == ["tValid"]


def test_first_label_routine_name_skipped() -> None:
    # The HELLOTST entry-point label itself is not a test case.
    cases = find_test_cases(Path("HELLOTST.m"), HELLOTST_SRC)
    assert "HELLOTST" not in [c.label for c in cases]


def test_label_with_wrong_formals_skipped() -> None:
    src = dedent("""\
        HELLOTST
                quit
                ;
        tBad(x,y)
                quit
                ;
        tGood(pass,fail)
                quit
    """).encode("ascii")
    cases = find_test_cases(Path("HELLOTST.m"), src)
    labels = [c.label for c in cases]
    assert labels == ["tGood"]


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------


def test_discover_finds_suite_under_directory(tmp_path: Path) -> None:
    suite = tmp_path / "HELLOTST.m"
    suite.write_bytes(HELLOTST_SRC)
    other = tmp_path / "HELLO.m"
    other.write_text("HELLO\n quit\n")
    suites = discover([tmp_path])
    assert len(suites) == 1
    assert suites[0].name == "HELLOTST"
    assert len(suites[0].cases) == 2


def test_discover_handles_explicit_file(tmp_path: Path) -> None:
    suite = tmp_path / "HELLOTST.m"
    suite.write_bytes(HELLOTST_SRC)
    suites = discover([suite])
    assert len(suites) == 1
    assert suites[0].name == "HELLOTST"


def test_discover_explicit_non_TST_file_still_parsed(tmp_path: Path) -> None:
    # If the user explicitly names a file we trust them, even if it doesn't
    # match the TST naming convention. (Useful for ad-hoc suites.)
    p = tmp_path / "EXAMPLE.m"
    p.write_bytes(HELLOTST_SRC.replace(b"HELLOTST", b"EXAMPLE"))
    suites = discover([p])
    assert len(suites) == 1
    assert suites[0].name == "EXAMPLE"


def test_discover_recurses(tmp_path: Path) -> None:
    nested = tmp_path / "tests" / "sub"
    nested.mkdir(parents=True)
    (nested / "ATST.m").write_bytes(HELLOTST_SRC.replace(b"HELLOTST", b"ATST"))
    suites = discover([tmp_path])
    names = sorted(s.name for s in suites)
    assert names == ["ATST"]


def test_discover_returns_suites_in_stable_order(tmp_path: Path) -> None:
    for name in ["ZTST", "ATST", "MTST"]:
        (tmp_path / f"{name}.m").write_bytes(HELLOTST_SRC.replace(b"HELLOTST", name.encode()))
    suites = discover([tmp_path])
    assert [s.name for s in suites] == ["ATST", "MTST", "ZTST"]


def test_TestSuite_dataclass_constructable() -> None:
    s = TestSuite(name="X", path=Path("X.m"), cases=[])
    assert s.name == "X"
    assert s.cases == []


def test_TestCase_dataclass_constructable() -> None:
    c = TestCase(suite="X", label="tFoo", description=None, path=Path("X.m"), line=1)
    assert c.suite == "X"
    assert c.label == "tFoo"
