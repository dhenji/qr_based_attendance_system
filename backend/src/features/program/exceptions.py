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
