"""The shared term-weeks resolver (D86).

Pure function, so these run as plain sync tests with no database — the same
hand-rolled style `test_shared_rates.py` uses. It matters because `term_weeks`
is now the single definition behind `expected_sessions`: the risk batch and the
offering read DTO both resolve through here, and `semester` is free text, so an
orphaned code must resolve to the default rather than raise or count zero.

Frozen here is the "never raise" contract — the value is a denominator, and a
`None` week count would either crash the nightly batch or (worse) read as a
zero expected-session total.
"""

from __future__ import annotations

from shared.schedule import DEFAULT_TERM_WEEKS, term_weeks

STRUCTURE = {
    "terms": [
        {"code": "1ST", "label": "First", "weeks": 9},
        {"code": "2ND", "label": "Second", "weeks": 12},
        {"code": "MID", "label": "Midyear"},
    ]
}


def test_resolves_the_matching_term() -> None:
    assert term_weeks(STRUCTURE, "1ST") == 9
    assert term_weeks(STRUCTURE, "2ND") == 12


def test_code_is_matched_after_stripping() -> None:
    assert term_weeks(STRUCTURE, "  1ST  ") == 9


def test_term_without_weeks_falls_back() -> None:
    assert term_weeks(STRUCTURE, "MID") == DEFAULT_TERM_WEEKS


def test_orphan_code_falls_back() -> None:
    """`semester` is free text with no vocabulary, so this is reachable."""

    assert term_weeks(STRUCTURE, "3RD") == DEFAULT_TERM_WEEKS


def test_missing_structure_falls_back() -> None:
    assert term_weeks(None, "1ST") == DEFAULT_TERM_WEEKS
    assert term_weeks({}, "1ST") == DEFAULT_TERM_WEEKS


def test_malformed_structure_falls_back() -> None:
    assert term_weeks({"terms": "nope"}, "1ST") == DEFAULT_TERM_WEEKS  # type: ignore[arg-type]
    assert term_weeks({"terms": [None, 3]}, "1ST") == DEFAULT_TERM_WEEKS  # type: ignore[list-item]


def test_non_positive_or_boolean_weeks_fall_back() -> None:
    """`bool` is an `int` subclass; a stray `True` must not count as 1 week."""

    assert term_weeks({"terms": [{"code": "1ST", "weeks": 0}]}, "1ST") == 18
    assert term_weeks({"terms": [{"code": "1ST", "weeks": -3}]}, "1ST") == 18
    assert term_weeks({"terms": [{"code": "1ST", "weeks": True}]}, "1ST") == 18


def test_custom_default_is_honored() -> None:
    assert term_weeks(None, "1ST", default=6) == 6
