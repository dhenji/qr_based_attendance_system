"""Term-scoped session weeks (D86).

Session weeks move from a per-offering column to the term entry in
`year_levels.term_structure` (`{"code", "label", "weeks"}`); the risk batch
and the offering read DTO now derive `expected_sessions` from the term. This
drops `course_offerings.semester_weeks`.

Fixing forward per ADR-065. To avoid silently changing existing absence-rate
denominators, the term weeks are backfilled *before* the column disappears:
for every `(year_level_id, semester)` referenced by offerings, the term
entry's `weeks` is set to the modal (most common) value among that term's
offerings. Pre-D86 drift means offerings could disagree; the modal value wins
(deterministic tie-break: higher week count, then value). A `(year_level,
semester)` pair with no matching term entry (orphaned free-text semester) is
left alone — the shared resolver falls back to `DEFAULT_TERM_WEEKS`.

Downgrade re-adds the column as NOT NULL with a temporary server default so it
succeeds on rows created while it was gone; the default is dropped immediately
after. It is lossy (per-offering overrides are not restored), which is
documented rather than silently accepted.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill_term_weeks(bind: sa.engine.Connection) -> None:
    rows = bind.execute(
        sa.text(
            "SELECT year_level_id, semester, semester_weeks "
            "FROM course_offerings WHERE semester_weeks IS NOT NULL"
        )
    ).fetchall()

    by_term: dict[tuple[int, str], Counter[int]] = {}
    for year_level_id, semester, weeks in rows:
        by_term.setdefault((int(year_level_id), str(semester).strip()), Counter())[
            int(weeks)
        ] += 1

    if not by_term:
        return

    years = bind.execute(
        sa.text("SELECT id, term_structure FROM year_levels")
    ).fetchall()

    for year_id, structure in years:
        if not isinstance(structure, dict):
            continue

        terms = structure.get("terms")
        if not isinstance(terms, list):
            continue

        changed = False
        for term in terms:
            if not isinstance(term, dict):
                continue

            code = str(term.get("code", "")).strip()
            counter = by_term.get((int(year_id), code))
            if not counter:
                continue

            # Modal value; deterministic tie-break so a re-run is stable.
            term["weeks"] = max(counter.items(), key=lambda kv: (kv[1], kv[0]))[0]
            changed = True

        if changed:
            bind.execute(
                sa.text(
                    "UPDATE year_levels SET term_structure = CAST(:s AS jsonb) "
                    "WHERE id = :id"
                ),
                {"s": json.dumps(structure), "id": int(year_id)},
            )


def upgrade() -> None:
    _backfill_term_weeks(op.get_bind())
    op.drop_column("course_offerings", "semester_weeks")


def downgrade() -> None:
    op.add_column(
        "course_offerings",
        sa.Column(
            "semester_weeks",
            sa.Integer(),
            nullable=False,
            server_default="18",
        ),
    )
    op.alter_column("course_offerings", "semester_weeks", server_default=None)
