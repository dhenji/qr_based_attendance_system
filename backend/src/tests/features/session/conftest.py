"""A pinned clock for the session tests (D94).

The suite as a whole pins the session service's clock (see the root
`conftest.py`), because a session may only be opened while its class is
running: left to the wall clock, the default offering (`MWF 08:00-09:00`)
would only be inside its window for three hours a week.

This package goes one step further and uses the same instant as its `now`
fixture, so the factories, the expiry stamps and the overrides all agree on
one clock. The tests that schedule a class at other hours move their own
fixtures to cover it — the weekly-hours totals they depend on do not change.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from tests.conftest import SESSION_TEST_NOW as SESSION_NOW


@pytest.fixture
def now() -> datetime:
    """The package's notion of now, for the factories and the assertions."""

    return SESSION_NOW
