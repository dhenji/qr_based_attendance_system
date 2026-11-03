"""The shared attendance-rate helper.

Pure functions, so these run as plain sync tests with no database — the same
hand-rolled style the other `shared/` tests use. Worth having in their own right
because `attendance_rates` now has nine call sites across four features and none
of them can pin its contract on its own: every feature test reaches it with a
non-negative, COUNT-derived `enrolled`, so the degenerate-denominator guard is
only reachable from here.

The compliance/participation distinction is the other thing worth freezing. Both
numbers appear in reports and on the admin dashboard, and quietly swapping the
numerator produces a *more flattering* number rather than an obvious error — which
is why a mutation that did exactly that is caught by
`test_compliance_counts_present_only`.
"""

from __future__ import annotations

import pytest

from shared.rates import attendance_rates


def test_compliance_counts_present_only() -> None:
    """Late and excused arrivals must not make compliance look better."""

    compliance, _ = attendance_rates(present=2, late=1, excused=1, enrolled=4)

    assert compliance == 0.5


def test_participation_credits_late_and_excused() -> None:
    """Compliance answers "on time"; participation answers "accounted for"."""

    _, participation = attendance_rates(present=2, late=1, excused=1, enrolled=4)

    assert participation == 1.0


def test_rates_are_rounded_to_four_places() -> None:
    """They land on Decimal(5, 4) columns and are compared in report tests."""

    compliance, participation = attendance_rates(
        present=1, late=0, excused=0, enrolled=3
    )

    assert compliance == 0.3333
    assert participation == 0.3333


@pytest.mark.parametrize("enrolled", [0, -1, -100])
def test_a_degenerate_denominator_is_zero_not_an_error(enrolled: int) -> None:
    """`enrolled` is COUNT-derived today, so negative is unreachable in practice.

    The guard is `<= 0` rather than `== 0` anyway: a caller that later passes a
    computed difference should get `(0.0, 0.0)` instead of a negative rate or a
    `ZeroDivisionError`.
    """

    assert attendance_rates(present=1, late=1, excused=1, enrolled=enrolled) == (
        0.0,
        0.0,
    )


def test_full_and_empty_attendance() -> None:
    assert attendance_rates(present=4, late=0, excused=0, enrolled=4) == (1.0, 1.0)
    assert attendance_rates(present=0, late=0, excused=0, enrolled=4) == (0.0, 0.0)


def test_arguments_are_keyword_only() -> None:
    """Two of the three counts are easy to swap, so the signature prevents it.

    The old `_session_service._rates` took `(enrolled, counts)` against everyone
    else's `(present, late, excused, enrolled)`; positional arguments would let
    the next transposed call compile silently.
    """

    with pytest.raises(TypeError):
        attendance_rates(1, 0, 0, 2)  # type: ignore[misc]
