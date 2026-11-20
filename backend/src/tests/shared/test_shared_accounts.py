"""The shared account display identity.

`Account` replaces the `_Account` copies in the excuse queue and the audit read
model. They were not identical: the audit model trimmed whitespace-only name
parts while the excuse queue joined stored parts verbatim. These tests pin both
formats and the student-first/professor-fallback resolution.
"""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy.dialects import sqlite

from shared.accounts import Account, account_from_row, account_query


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=7, email="ada@example.test", role="student")


def test_account_name_prefers_the_roster_name() -> None:
    account = Account(
        id=7, email="ada@example.test", first_name="Ada", last_name="Lovelace"
    )

    assert account.name == "Ada Lovelace"


def test_account_name_falls_back_to_email() -> None:
    account = Account(id=7, email="ada@example.test")

    assert account.name == "ada@example.test"


def test_excuse_format_joins_stored_name_parts_verbatim() -> None:
    """The excuse queue's historical behavior did not trim stored parts."""

    account = Account(
        id=7, email="ada@example.test", first_name=" Ada", last_name="Lovelace "
    )

    assert account.name == " Ada Lovelace "


def test_audit_format_ignores_whitespace_only_parts() -> None:
    account = Account(
        id=7,
        email="ada@example.test",
        first_name=" ",
        last_name="Lovelace",
        _trim_name_parts=True,
    )

    assert account.name == "Lovelace"


def test_account_from_row_prefers_the_student_name() -> None:
    row = (_user(), "Ada", "Lovelace", "Prof", "Assistant")

    account = account_from_row(row)

    assert account.id == 7
    assert account.email == "ada@example.test"
    assert account.role == "student"
    assert account.first_name == "Ada"
    assert account.last_name == "Lovelace"


def test_account_from_row_falls_back_to_the_professor_name() -> None:
    row = (_user(), None, None, "Prof", "Assistant")

    account = account_from_row(row)

    assert account.first_name == "Prof"
    assert account.last_name == "Assistant"


def test_trimmed_account_falls_back_to_email() -> None:
    account = account_from_row((_user(), " ", "  ", None, None), trim_name_parts=True)

    assert account.name == "ada@example.test"


def test_account_query_outer_joins_both_rosters() -> None:
    sql = str(account_query().compile(dialect=sqlite.dialect()))

    assert "LEFT OUTER JOIN students" in sql
    assert "LEFT OUTER JOIN professors" in sql
