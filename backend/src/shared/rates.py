from __future__ import annotations

"""The one definition of attendance compliance and participation rates.

Four features computed these independently and the copies had already begun
to diverge: `analytics` and `reports` had byte-identical bodies, `attendance`
had the same body renamed to `_history_rates`, and `session` had a variant with
the arguments *transposed* — `(enrolled, counts)` against everyone else's
`(present, late, excused, enrolled)`. A reader arriving at the session copy had
no way to know it was the odd one out.

`attendance_rates` is that single definition. Four properties are deliberate:

- **Keyword-only.** Two of the three counts are easy to swap and the compiler
  cannot catch `attendance_rates(late, present, excused, enrolled)`. The
  transposed session signature is exactly the failure this prevents; positional
  arguments would let the next one in.
- **`(0.0, 0.0)` for an empty denominator.** A student with no enrollments, a
  session nobody scanned, a professor with no courses. Every call site would
  otherwise repeat the guard, and one of them eventually would not.
- **Rounded to 4 places.** These are stored on `Decimal(5, 4)` columns and
  serialised into reports, so the rounding belongs with the calculation rather
  than at each call site.
- **Compliance vs participation.** Compliance is `present / enrolled`;
  participation adds `late` and `excused`, i.e. everything that produced a
  record of the student being there in some form. Confusing the two is how a
  dashboard ends up reporting a flattering number, so the docstring says which
  is which.

`session` passes a `SessionCounts` and `attendance` a `HistoryCounts`; both
unpack at the call site, which is the right place for that — the shape of a
count bundle is each feature's business, the arithmetic is not.
"""


def attendance_rates(
    *,
    present: int,
    late: int,
    excused: int,
    enrolled: int,
) -> tuple[float, float]:
    """Return `(compliance_rate, participation_rate)`, both rounded to 4 places.

    Compliance is the strict one: present and nothing else, over the number of
    students enrolled. Participation also credits late arrivals and approved
    excuses, so it answers "did we account for this student" where compliance
    answers "was this student on time".
    """

    if enrolled <= 0:
        return 0.0, 0.0

    compliance: float = round(present / enrolled, 4)
    participation: float = round((present + late + excused) / enrolled, 4)

    return compliance, participation
