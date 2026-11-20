"""Cross-feature exceptions.

Feature slices own their own `exceptions.py`; a rule that is enforced
identically by several slices lives here so the contract has one definition.
"""

from __future__ import annotations

from core.exceptions import DomainException


class PdfExportUnavailableException(DomainException):
    """422 - the requested export format has no writer installed.

    The analytics, system, and professor reports exports all accept only CSV.
    Keeping the message, code, and field in one class means the three
    download endpoints cannot drift apart into three different 422s.
    """

    code: str = "validation_error"

    def __init__(self) -> None:
        super().__init__(
            message="PDF export is not available yet; request format csv",
            field="format",
        )
