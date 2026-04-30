"""Tests for m_cli.lint.thresholds — defaults + validation.

The thresholds module is the single source of truth for the
configurable numeric limits used by the M-MOD modernization rules.
These tests pin the default values and the validation behavior so
neither can drift silently.
"""

from __future__ import annotations

import pytest

from m_cli.lint.thresholds import KNOWN_THRESHOLDS, validate


class TestDefaults:
    def test_known_thresholds_includes_phase2_keys(self):
        # The four keys consumed by M-MOD-001..004 must always be
        # present. Adding a key is fine; removing one is a deliberate
        # API change and should fail this test.
        for key in ("line_length", "code_line_length", "routine_lines", "label_lines"):
            assert key in KNOWN_THRESHOLDS

    def test_default_values_are_modern(self):
        # Sanity-check the modern defaults — a regression here likely
        # means someone resurrected a 1980s SAC limit by accident.
        assert KNOWN_THRESHOLDS["line_length"] == 200
        assert KNOWN_THRESHOLDS["code_line_length"] == 1000
        assert KNOWN_THRESHOLDS["routine_lines"] == 1000
        assert KNOWN_THRESHOLDS["label_lines"] == 50

    def test_all_defaults_are_positive_ints(self):
        for key, val in KNOWN_THRESHOLDS.items():
            assert isinstance(val, int), f"{key}: {val!r} is not int"
            assert not isinstance(val, bool), f"{key}: bool sneaked in"
            assert val > 0, f"{key}: {val!r} not positive"


class TestValidate:
    def test_none_returns_pure_defaults(self):
        out = validate(None)
        assert out == KNOWN_THRESHOLDS
        # Returns a copy, not the dict itself — caller must not mutate
        # the source-of-truth.
        assert out is not KNOWN_THRESHOLDS

    def test_empty_dict_returns_defaults(self):
        assert validate({}) == KNOWN_THRESHOLDS

    def test_partial_override_fills_in_defaults(self):
        out = validate({"line_length": 80})
        assert out["line_length"] == 80
        assert out["code_line_length"] == KNOWN_THRESHOLDS["code_line_length"]
        assert out["routine_lines"] == KNOWN_THRESHOLDS["routine_lines"]
        assert out["label_lines"] == KNOWN_THRESHOLDS["label_lines"]

    def test_full_override_replaces_all(self):
        # Override every known threshold; result should equal the
        # overrides dict (no defaults filled in because nothing is
        # missing).
        overrides = {key: 99 for key in KNOWN_THRESHOLDS}
        out = validate(overrides)
        assert out == overrides

    def test_unknown_key_raises_with_known_list(self):
        with pytest.raises(ValueError) as exc:
            validate({"line_lenght": 80})  # typo
        msg = str(exc.value)
        assert "line_lenght" in msg
        assert "line_length" in msg  # the correct one is listed

    def test_zero_is_rejected(self):
        with pytest.raises(ValueError, match="positive integer"):
            validate({"line_length": 0})

    def test_negative_is_rejected(self):
        with pytest.raises(ValueError, match="positive integer"):
            validate({"line_length": -1})

    def test_bool_is_rejected(self):
        # bool is a subclass of int in Python — easy to slip in by accident.
        with pytest.raises(ValueError, match="positive integer"):
            validate({"line_length": True})

    def test_non_int_is_rejected(self):
        with pytest.raises(ValueError, match="positive integer"):
            validate({"line_length": "200"})  # string, not int

    def test_validate_does_not_mutate_input(self):
        overrides = {"line_length": 100}
        validate(overrides)
        assert overrides == {"line_length": 100}
