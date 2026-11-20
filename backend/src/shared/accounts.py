"""The display identity of a `users` row, shared by every slice that reads one.

`users` has no name columns: a person's name lives on their student or
professor row, so an account is rendered by outer-joining those roster rows.
`account_query` is that join and `account_from_row` is the resolution.

The two roster names cannot both be trusted on a malformed pair of rows, so
the student name wins exactly as the admin user list, the audit read model, and
the excuse queue already resolved it. The audit model also ignores
whitespace-only name parts while the excuse queue joins stored parts verbatim;
`trim_name_parts` keeps that existing difference rather than flattening it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Select, select

from features.auth.model import User
from features.professor.model import Professor
from features.student.model import Student


@dataclass
class Account:
    """A `users` row with the name its roster carries, if any.

    The `users` table has no name columns — a person's name lives on their
    student or professor row — so the name is outer-joined in.
    """

    id: int
    email: str
    first_name: str | None = None
    last_name: str | None = None
    role: str | None = None
    _trim_name_parts: bool = field(default=False, repr=False, compare=False)

    @property
    def name(self) -> str:
        if self._trim_name_parts:
            joined = " ".join(
                part
                for part in (self.first_name, self.last_name)
                if part and part.strip()
            ).strip()
        else:
            joined = " ".join(
                part for part in (self.first_name, self.last_name) if part
            )
        return joined or self.email


def account_query(*columns: Any) -> Select[Any]:
    """A `users` select with the optional roster name columns outer-joined.

    With no explicit projection it returns `User` followed by the four roster
    name columns in `account_from_row` order. Callers that only need account
    ids pass `User.id`.
    """
    projection = columns or (
        User,
        Student.first_name,
        Student.last_name,
        Professor.first_name,
        Professor.last_name,
    )
    return (
        select(*projection)
        .outerjoin(Student, Student.user_id == User.id)
        .outerjoin(Professor, Professor.user_id == User.id)
    )


def account_from_row(row: Sequence[Any], *, trim_name_parts: bool = False) -> Account:
    """Resolve one `account_query` row, preferring the student name."""
    user: User = row[0]
    return Account(
        id=user.id,
        email=user.email,
        first_name=row[1] or row[3],
        last_name=row[2] or row[4],
        role=user.role,
        _trim_name_parts=trim_name_parts,
    )
