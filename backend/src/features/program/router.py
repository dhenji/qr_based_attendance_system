from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from api.deps import ProgramServiceDep, require_role
from features.auth.model import User
from features.program.constants import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SEARCH_MAX_LENGTH,
)
from features.program.schema import (
    ProgramCreate,
    ProgramDetail,
    ProgramRead,
    ProgramUpdate,
    YearLevelCreate,
    YearLevelRead,
    YearLevelUpdate,
)
from shared.enums import UserRole
from shared.pagination import PaginatedResponse

# ALREADY MOUNTED at /api/admin/programs (see api/router.py), with no prefix=
# argument there - the contract path is baked in below. DO NOT change this prefix
# and DO NOT mount this router a second time.
#
# /admin/programs is the program slice's ONLY mount point, so year-level routes
# nest under this prefix as /admin/programs/{program_id}/years. Do not create a
# second APIRouter for this slice: paths inside a router are relative to its own
# prefix, so a second mount would re-register the five routes above.
#
# Collection routes below use "" not "/" so /admin/programs registers exactly,
# with no trailing-slash redirect.
router = APIRouter(prefix="/admin/programs")


@router.get(
    "",
    response_model=PaginatedResponse[ProgramRead],
    summary="List programs (search, status filter, derived aggregates, paginated)",
)
async def list_programs(
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProgramServiceDep,
    search: str | None = Query(default=None, max_length=SEARCH_MAX_LENGTH),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[ProgramRead]:
    return await service.list(search=search, is_active=is_active, page=page, size=size)


@router.post(
    "",
    response_model=ProgramRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a program",
)
async def create_program(
    payload: ProgramCreate,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProgramServiceDep,
) -> ProgramRead:
    return await service.create(payload=payload)


@router.get(
    "/{program_id}",
    response_model=ProgramDetail,
    summary="Get a program with its nested year levels",
)
async def get_program(
    program_id: int,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProgramServiceDep,
) -> ProgramDetail:
    return await service.get(program_id=program_id)


@router.patch(
    "/{program_id}",
    response_model=ProgramRead,
    summary="Update a program (name, description, is_active)",
)
async def update_program(
    program_id: int,
    payload: ProgramUpdate,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProgramServiceDep,
) -> ProgramRead:
    return await service.update(program_id=program_id, payload=payload)


@router.delete(
    "/{program_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive a program (is_active=false, no cascade)",
)
async def archive_program(
    program_id: int,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProgramServiceDep,
) -> None:
    await service.archive(program_id=program_id)


@router.get(
    "/{program_id}/years",
    response_model=PaginatedResponse[YearLevelRead],
    summary="List year levels of a program (paginated)",
)
async def list_year_levels(
    program_id: int,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProgramServiceDep,
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[YearLevelRead]:
    return await service.list_years(program_id=program_id, page=page, size=size)


@router.post(
    "/{program_id}/years",
    response_model=YearLevelRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a year level under a program",
)
async def create_year_level(
    program_id: int,
    payload: YearLevelCreate,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProgramServiceDep,
) -> YearLevelRead:
    return await service.create_year(program_id=program_id, payload=payload)


@router.get(
    "/{program_id}/years/{year_id}",
    response_model=YearLevelRead,
    summary="Get a year level of a program",
)
async def get_year_level(
    program_id: int,
    year_id: int,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProgramServiceDep,
) -> YearLevelRead:
    return await service.get_year(program_id=program_id, year_id=year_id)


@router.patch(
    "/{program_id}/years/{year_id}",
    response_model=YearLevelRead,
    summary="Update a year level (label, term_structure, sort_order)",
)
async def update_year_level(
    program_id: int,
    year_id: int,
    payload: YearLevelUpdate,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProgramServiceDep,
) -> YearLevelRead:
    return await service.update_year(
        program_id=program_id, year_id=year_id, payload=payload
    )


@router.delete(
    "/{program_id}/years/{year_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a year level (restrict if offerings reference it)",
)
async def delete_year_level(
    program_id: int,
    year_id: int,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProgramServiceDep,
) -> None:
    await service.delete_year(program_id=program_id, year_id=year_id)
