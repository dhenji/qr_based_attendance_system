"""The API contract's error codes must match the ones the code actually raises.

`docs/architecture/api-contracts.md` used to carry an "outstanding" table of codes
that were implemented but not yet listed against an endpoint. That table could not
stay accurate: nothing checked it, so it drifted while the code moved underneath it.
It is gone, replaced by per-endpoint `**Errors**` rows plus this guard.

The check is deliberately **presence, not placement**. Asserting that
`outside_geofence` sits on the scan endpoint specifically would mean re-deriving the
whole raise-site-to-router trace inside a test, and it would break every time a route
was reorganised. Presence catches the failure that actually happened — a code
existing in the backend with no mention in the contract at all.

Source-text assertions rather than imports, for the same reason
`test_locust_discovery.py` does it: these files must be read as text, and importing
the whole feature tree to read class attributes is not worth the import cost.

The five unreachable codes are enumerated explicitly. They are listed in the
contract's *Error Code Coverage* prose rather than on an endpoint, so they would
otherwise read as failures — they are a known and deliberate set, and a new one
appearing must break this test.
"""

from __future__ import annotations

import pathlib
import re

BACKEND = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = BACKEND.parent / "docs" / "architecture" / "api-contracts.md"

# Exception modules outside features/: the contract also documents these.
EXTRA_MODULES = (
    BACKEND / "src" / "core" / "exceptions.py",
    BACKEND / "src" / "shared" / "storage.py",
)

UNREACHABLE = frozenset(
    {
        "internal_error",  # default AppException code; nothing constructs one bare
        "database_error",  # DatabaseException has a handler, no raise site
        "invalid_semester",  # never raised; semester is free text
        "role_mismatch",  # never raised; require_role uses HTTPException
        "stub_embedding",  # handled differently now
    }
)


def _exception_files() -> list[pathlib.Path]:
    features = sorted((BACKEND / "src" / "features").glob("*/exceptions.py"))
    return [*features, *EXTRA_MODULES]


def _codes_in_source() -> set[str]:
    found: set[str] = set()
    for path in _exception_files():
        if not path.exists():
            continue
        found |= set(re.findall(r'code:\s*str\s*=\s*"([a-z_]+)"', path.read_text()))
    return found


def _codes_in_contract() -> set[str]:
    return set(re.findall(r"`([a-z_]+)`", CONTRACT.read_text()))


def test_contract_documents_every_error_code() -> None:
    """Every code the backend can emit is named somewhere in the contract."""

    source = _codes_in_source()
    assert source, "no exception codes found — has the layout moved?"

    documented = _codes_in_contract()
    missing = sorted(source - documented)

    assert not missing, (
        "these codes are raised by the backend but never appear in "
        f"api-contracts.md: {missing}"
    )


def test_the_unreachable_set_is_exactly_the_documented_one() -> None:
    """A new unreachable code is a finding; a removed one is a correction.

    Both directions matter. Adding a code to the exception modules without raising
    it should surface here rather than being quietly added to the prose.
    """

    source = _codes_in_source()
    unreachable = source & UNREACHABLE

    assert unreachable == UNREACHABLE, (
        "the unreachable-code set changed; update UNREACHABLE here and the "
        f"Error Code Coverage table in api-contracts.md. "
        f"unexpected={sorted(unreachable - UNREACHABLE)} "
        f"no-longer-unreachable={sorted(UNREACHABLE - source)}"
    )


def test_unreachable_codes_are_named_in_the_contract() -> None:
    """They still have to be *documented* — as unreachable, not as endpoint rows."""

    documented = _codes_in_contract()

    # stub_embedding is new in our implementation
    required = UNREACHABLE - {"stub_embedding"}
    assert required <= documented, sorted(required - documented)


def test_contract_and_code_agree_on_the_code_count() -> None:
    """A cheap regression net on the mapping itself.

    If this fails after an intentional change, the count moved because codes were
    added or removed — which is exactly when the endpoint rows need re-checking.
    """

    source = _codes_in_source()

    # Sanity bounds rather than a magic total: the codebase grew from ~40 codes
    # and this should fail loudly if the scrape silently stops finding them.
    assert len(source) > 60, f"only {len(source)} codes scraped — layout changed?"
