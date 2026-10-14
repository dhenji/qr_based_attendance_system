from __future__ import annotations

from core.exceptions import AppException, DomainException


class ProgramException(AppException):
    """Root umbrella for all program-module errors."""


class ProgramDomainException(ProgramException, DomainException):
    pass


class ProgramNotFoundException(ProgramDomainException):
    """404 - the target program does not exist."""

    status_code: int = 404
    code: str = "program_not_found"

    def __init__(self, program_id: int) -> None:
        super().__init__(message=f"Program {program_id} not found")


class ProgramCodeExistsException(ProgramDomainException):
    """409 - another program already uses this code.

    `programs.code` is unique, so the duplicate is rejected before the INSERT
    instead of letting the unique violation surface as a 500.
    """

    status_code: int = 409
    code: str = "program_code_exists"

    def __init__(self, code: str) -> None:
        super().__init__(message=f"Program code {code} already exists")


class ProgramNotArchivedException(ProgramDomainException):
    """409 - only archived (`is_active=false`) programs may be hard-deleted."""

    status_code: int = 409
    code: str = "not_archived"

    def __init__(self, program_id: int) -> None:
        super().__init__(
            message=f"Program {program_id} is still active and cannot be deleted"
        )


class ProgramHasOfferingsException(ProgramDomainException):
    """409 - course offerings still reference this program.

    `course_offerings.program_id` is `ondelete="RESTRICT"`, so the delete is
    rejected before the FK violation surfaces as a 500.
    """

    status_code: int = 409
    code: str = "program_has_offerings"

    def __init__(self, program_id: int) -> None:
        super().__init__(
            message=f"Program {program_id} has offerings and cannot be deleted"
        )


class ProgramHasStudentsException(ProgramDomainException):
    """409 - students are still enrolled under this program's year levels.

    Students reference `year_levels.id` (`ondelete="RESTRICT"`) and resolve
    their program transitively via `year_levels.program_id`, so the delete is
    rejected before the FK violation surfaces as a 500.
    """

    status_code: int = 409
    code: str = "program_has_students"

    def __init__(self, program_id: int) -> None:
        super().__init__(
            message=f"Program {program_id} has students and cannot be deleted"
        )


class YearLevelNotFoundException(ProgramDomainException):
    """404 - the year level does not exist under this program.

    Year levels are owned by the program slice, so this class lives here rather
    than in a second exceptions module: the nested
    /admin/programs/{program_id}/years routes reuse it.
    """

    status_code: int = 404
    code: str = "year_level_not_found"

    def __init__(self, year_level_id: int, program_id: int | None = None) -> None:
        if program_id is None:
            super().__init__(message=f"Year level {year_level_id} not found")
            return

        super().__init__(
            message=f"Year level {year_level_id} not found under program {program_id}"
        )


class YearLevelNumberExistsException(ProgramDomainException):
    """409 - this program already has a year level with this year_number.

    `(program_id, year_number)` carries the `uq_program_year_number` unique
    constraint, so the duplicate is rejected before the INSERT instead of letting the unique violation surface as a 500.
    """

    status_code: int = 409
    code: str = "year_number_exists"

    def __init__(self, year_number: int, program_id: int) -> None:
        super().__init__(
            message=f"Year level {year_number} already exists under program {program_id}"
        )


class YearLevelHasCoursesException(ProgramDomainException):
    """409 - the year level still has course offerings referencing it.

    `course_offerings.year_level_id` is `ondelete="RESTRICT"`, so the delete is rejected before the FK violation surfaces as a 500.
    """

    status_code: int = 409
    code: str = "year_has_courses"

    def __init__(self, year_level_id: int) -> None:
        super().__init__(
            message=f"Year level {year_level_id} has courses and cannot be deleted"
        )
