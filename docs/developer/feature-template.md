# Feature Template — Vertical Slice Checklist

> Step-by-step guide for adding a new feature to the QR Attendance System.
> Uses `program/` as the worked example.

---

## Overview

Every feature follows the **vertical slice** pattern:

```
backend/src/features/{feature}/
├── __init__.py
├── model.py        # SQLAlchemy ORM models
├── schema.py       # Pydantic v2 request/response schemas
├── service.py      # Business logic
└── router.py       # FastAPI endpoints
```

Plus an Alembic migration, a frontend feature slice, and backend tests.

---

## Checklist

### 1. Model (`backend/src/features/{feature}/model.py`)

Define SQLAlchemy ORM models inheriting from `core.database.Base`.

**Worked example — `program/model.py`:**

```python
from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from shared.mixins import TimestampMixin


class Program(TimestampMixin, Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    total_years: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())

    year_levels: Mapped[list["YearLevel"]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )


class YearLevel(Base):
    __tablename__ = "year_levels"
    __table_args__ = (
        UniqueConstraint("program_id", "year_number", name="uq_program_year_number"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    program_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    year_number: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(50))
    term_structure: Mapped[dict] = mapped_column(JSONB)
    sort_order: Mapped[int] = mapped_column(Integer)

    program: Mapped["Program"] = relationship(back_populates="year_levels")
```

> `YearLevel` is a plain `Base` subclass, **not** `TimestampMixin` — the real
> table has no `updated_at`. Check the target schema in
> [database-er.md](../design/database-er.md) before adding mixins.

**Conventions:**

- Use `BigInteger` for PKs and FKs
- Use `Mapped[type]` with `mapped_column()` (SQLAlchemy 2.0 style)
- Inherit `TimestampMixin` from `shared/mixins.py` for `created_at`/`updated_at`
- Use `String(n)` for bounded strings, `Text` for unbounded
- FK `ondelete` rule: `CASCADE` for owned children, `RESTRICT` for references
- Import `Base` from `core.database`
- Avoid `Computed`/`GENERATED` columns that reference other columns with `server_default` (e.g., `created_at` with `func.now()`) — compute in service layer instead (see D49)

**Done:**

- [ ] Model class defined with correct `__tablename__`
- [ ] PK, columns, FKs match the [target schema](../design/database-er.md)
- [ ] Relationships defined where needed
- [ ] `TimestampMixin` inherited for entities that need it

---

### 2. Alembic Migration

```bash
cd backend
alembic revision --autogenerate -m "create {feature} tables"
```

**Critical:** Import the new model in `backend/alembic/env.py`:

```python
import features.program.model  # noqa: F401
```

Apply:

```bash
cd backend
alembic upgrade head
```

**Done:**

- [ ] Model imported in `alembic/env.py`
- [ ] Migration generated and reviewed
- [ ] `alembic upgrade head` succeeds
- [ ] Rollback tested: `alembic downgrade -1` succeeds

---

### 3. Schemas (`backend/src/features/{feature}/schema.py`)

Pydantic v2 models for request/response validation.

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from features.admin.constants import NAME_MAX_LENGTH, NAME_MIN_LENGTH
from features.program.constants import (
    CODE_MAX_LENGTH,
    CODE_MIN_LENGTH,
    DESCRIPTION_MAX_LENGTH,
    TOTAL_YEARS_MAX,
    TOTAL_YEARS_MIN,
)


class ProgramCreate(BaseModel):
    code: str = Field(min_length=CODE_MIN_LENGTH, max_length=CODE_MAX_LENGTH)
    name: str = Field(min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    total_years: int = Field(ge=TOTAL_YEARS_MIN, le=TOTAL_YEARS_MAX)


class ProgramRead(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None
    total_years: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProgramUpdate(BaseModel):
    # `code` and `total_years` are absent, not Optional: neither is mutable.
    name: str | None = Field(
        default=None, min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH
    )
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    is_active: bool | None = None
```

**Conventions:**

- Separate `Create`, `Read`, `Update` schemas per entity
- `Read` uses `ConfigDict(from_attributes=True)` for ORM compatibility
- Use `Field(...)` for constraints (`ge`, `le`, `min_length`, `max_length`)
- **Every field bound is a named constant from the slice's `constants.py`** — never an inline
  literal. Bounds shared with another slice are re-exported from that slice's constants
  (`NAME_MAX_LENGTH` lives in `features/admin/constants.py`, not in the slice that uses it),
  which is ADR-058(b).
- **`Update` omits immutable fields entirely** rather than making them `| None`. A `| None`
  field is indistinguishable from "not supplied", so `code` or `total_years` on `Update`
  would silently accept a change the service must then reject.
- Never return passwords or secrets in `Read` schemas

**Done:**

- [ ] Create/Read/Update schemas defined
- [ ] Field constraints match business rules
- [ ] No sensitive data exposed in Read schema

---

### 4. Service (`backend/src/features/{feature}/service.py`)

Business logic layer. No HTTP concerns — receives an `AsyncSession` and returns **read
schemas**. This is a service **class**: `__init__` composes one `BaseCRUD` handle per model it
touches, so the router never constructs it (see `coding-standards.md` §1.7).

```python
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from features.program.exceptions import ProgramCodeExistsException
from features.program.model import Program, YearLevel
from features.program.schema import ProgramCreate, ProgramRead
from shared.audit import record_audit
from shared.base import BaseCRUD
from shared.enums import AuditAction, AuditEntity
from shared.pagination import PaginatedResponse
from shared.query import apply_if


class ProgramService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._programs: BaseCRUD[Program] = BaseCRUD(Program, session)
        self._years: BaseCRUD[YearLevel] = BaseCRUD(YearLevel, session)

    async def create(
        self, *, payload: ProgramCreate, actor_id: int | None = None
    ) -> ProgramRead:
        if await self._programs.get_by(code=payload.code) is not None:
            raise ProgramCodeExistsException(payload.code)

        program: Program = await self._programs.create(
            code=payload.code,
            name=payload.name,
            description=payload.description,
            total_years=payload.total_years,
        )

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.CREATE,
            entity_type=AuditEntity.PROGRAM,
            entity_id=program.id,
            new_value=self._snapshot(program),
        )

        return ProgramRead(**self._read_fields(program))

    async def list(
        self, *, search: str | None, is_active: bool | None, page: int, size: int
    ) -> PaginatedResponse[ProgramRead]:
        stmt: Select[tuple[Program]] = self._list_stmt(
            search=search, is_active=is_active
        )

        total: int = (
            await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
            or 0
        )
        rows = (
            await self._session.scalars(
                stmt.order_by(Program.id).offset((page - 1) * size).limit(size)
            )
        ).all()

        return PaginatedResponse[ProgramRead](
            items=[ProgramRead(**self._read_fields(p)) for p in rows],
            total=total,
            page=page,
            size=size,
        )

    async def _get_or_404(self, program_id: int) -> Program:
        program = await self._programs.get(program_id)
        if program is None:
            raise ProgramNotFoundException(program_id)
        return program

    @staticmethod
    def _list_stmt(*, search: str | None, is_active: bool | None) -> Select[tuple[Program]]:
        stmt: Select[tuple[Program]] = select(Program)
        stmt = apply_if(stmt, is_active, lambda v: Program.is_active == v)

        if search:
            term: str = f"%{search.strip()}%"
            stmt = stmt.where(or_(Program.code.ilike(term), Program.name.ilike(term)))

        return stmt
```

The router reaches it through an annotated dependency, so the transaction boundary is
unchanged (`api/deps.py`):

```python
async def _get_program_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> ProgramService:
    return ProgramService(session)


ProgramServiceDep = Annotated[ProgramService, Depends(_get_program_service)]
```

**Conventions:**

- A slice service is a `class <Feature>Service`; `__init__` builds one `BaseCRUD` handle per
  model it touches and holds no state across requests. All 15 services in the tree are classes.
- **The class name carries the noun, so methods do not repeat it** — `create`, `get`, `list`,
  `archive`, not `create_program`. Sub-resources extend it: `list_years`, `create_year`.
- **Keyword-only arguments after `self`,** and payloads arrive as the Create schema rather than
  as loose scalars.
- **Every list returns `PaginatedResponse[T]`** with an explicit `total` count, and takes
  `page`/`size` bounds from `shared/pagination.py`. `BaseCRUD.list()` has its own `limit=50`
  default and is for internal lookups — do not return it from a list endpoint.
- Use `apply_if(stmt, value, build)` for optional filters; it skips building a criterion for a
  `None` value, which a bare comparison would reject at construction time.
- **Return read schemas.** `model_validate` cannot see derived aggregates, so a response that
  carries counts or collections is built as `ProgramRead(**self._read_fields(row))`.
- **Sensitive mutations call `record_audit(...)`** in the caller's transaction, so the audit
  row rolls back with the change it describes.
- **`await session.flush()` after writes — never `commit()` and never `refresh()`**
- Raise **domain exceptions** from `exceptions.py` — never `HTTPException`, never a raw
  `ValueError`. Only `AppException` subclasses reach the client's `{detail: {code, message}}`
  envelope; `HTTPException` belongs to the auth layer in `api/deps.py`.
- Keep methods focused — one operation per method

> **Do not call `session.commit()` in a service.** The single `commit()` lives in
> the `_get_db` dependency (`backend/src/api/deps.py`), which commits on success
> and rolls back on any `AppException`. A service-level commit breaks that
> rollback contract and makes `flush`-then-raise patterns silently persist.

**Done:**

- [ ] CRUD operations implemented
- [ ] Business rules enforced (not in router)
- [ ] Database session passed as parameter (not global)
- [ ] No `commit()` / `refresh()` in the service

---

### 5. Router (`backend/src/features/{feature}/router.py`)

FastAPI router with endpoint definitions.

```python
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
from features.program.schema import ProgramCreate, ProgramRead
from shared.enums import UserRole
from shared.pagination import PaginatedResponse

# The full contract path lives here, not in api/router.py: it passes no prefix=
# argument. Collection routes below use "" not "/" so /admin/programs registers
# exactly, with no trailing-slash redirect.
router = APIRouter(prefix="/admin/programs")


@router.get(
    "",
    response_model=PaginatedResponse[ProgramRead],
    summary="List programs (search, status filter, paginated)",
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
    user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProgramServiceDep,
) -> ProgramRead:
    return await service.create(payload=payload, actor_id=user.id)


@router.get("/{program_id}", response_model=ProgramRead, summary="Get one program")
async def get_program(
    program_id: int,
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    service: ProgramServiceDep,
) -> ProgramRead:
    return await service.get(program_id=program_id)
```

The 404 is the service's job — `service.get()` raises `ProgramNotFoundException`, which the
`AppException` handler renders as `{"detail": {"code": "program_not_found", "message": ...}}`.
**A router never constructs a 404 by hand**, because a bare
`HTTPException(status_code=404, detail="...")` puts a plain string where the frontend's error
parser expects `{code, message}`. Note the role-guard parameter is named `user` (not `_`) when
the handler forwards `actor_id=user.id` to the service for the audit row.

**Conventions:**

- Prefix matches [API contract](../architecture/api-contracts.md) and is **baked
  into the router**; `api/router.py` must not pass a `prefix=` argument
- **Collection routes are declared `""`, never `"/"`** — `"/"` registers a trailing-slash
  redirect the contract does not have
- The service arrives through its `*ServiceDep`; the router never constructs it
- The session dependency is **`_get_db`** — there is no public `get_db`
- The admin CRUD route set is `GET ""`, `POST ""`, `GET /{id}`, `PATCH /{id}`,
  `DELETE /{id}` — in that order in the module, each with a one-line `summary=`
- **Every admin route carries its own role guard**:
  `_: Annotated[User, Depends(require_role(UserRole.ADMIN))]`. `super_admin` passes
  automatically, so routes never name both roles
- Pagination and search bounds are declared per route via `Query(...)` so they appear in the
  OpenAPI schema. **Import those constants from the slice's `constants.py`**, which
  re-exports `shared/pagination.py` and `SEARCH_MAX_LENGTH` (ADR-058b) — the router should
  not reach into `shared/` for feature-specific bounds
- Response model is the Read schema (`PaginatedResponse[...]` for lists)
- **Errors come from the service's domain exceptions.** Only `AppException` has a handler;
  `DomainException` maps to 422 and `DatabaseException` to 409 automatically
- Tags group endpoints in Swagger UI

**Done:**

- [ ] Endpoints match the [API contract](../architecture/api-contracts.md)
- [ ] Request/response schemas used correctly
- [ ] Error responses consistent (`{detail: {code, message}}`)
- [ ] No collection route declared with `"/"`

#### One `APIRouter` per (feature, mount point)

A router's prefix is its full contract path, so **one `APIRouter` serves exactly
one mount point**. Most features need only one router. When a single feature's
endpoints span two prefixes, declare a **second `APIRouter` in its own module**
rather than mounting the same router twice. All 23 mounted routers:

| Router module                            | Prefix                 |
| ---------------------------------------- | ---------------------- |
| `features/auth/router.py`                | `/auth`                |
| `features/student/router.py`             | `/student`             |
| `features/session/router.py`             | `/professor`           |
| `features/attendance/router.py`          | `/student`             |
| `features/attendance/admin_router.py`    | `/admin/attendance`    |
| `features/professor/router.py`           | `/professor`           |
| `features/program/router.py`             | `/admin/programs`      |
| `features/admin/router.py`               | `/admin/users`         |
| `features/student/admin_router.py`       | `/admin/students`      |
| `features/professor/admin_router.py`     | `/admin/professors`    |
| `features/course/router.py`              | `/admin/courses`       |
| `features/course/offering_router.py`     | `/admin/offerings`     |
| `features/face_enrollment/router.py`     | `/admin/face-enrollment` |
| `features/excuse/professor_router.py`    | `/professor`           |
| `features/excuse/student_router.py`      | `/student`             |
| `features/excuse/admin_router.py`        | `/admin/excuses`       |
| `features/upload/router.py`              | `/upload`              |
| `features/analytics/router.py`           | `/admin/analytics`     |
| `features/reports/router.py`             | `/professor`           |
| `features/system/router.py`              | `/admin`               |
| `features/dashboard/student_router.py`   | `/student`             |
| `features/dashboard/professor_router.py` | `/professor`           |
| `features/dashboard/admin_router.py`     | `/admin`               |

These 23 routers collapse onto **15 distinct mount paths**, because a mount point is a
namespace rather than an owner:

| Mount path      | Routers sharing it                                                     |
| --------------- | ---------------------------------------------------------------------- |
| `/api/student`  | `student`, `attendance`, `excuse/student`, `dashboard/student` (4)      |
| `/api/professor`| `professor`, `session`, `excuse/professor`, `reports`, `dashboard/professor` (5) |
| `/api/admin`    | `system`, `dashboard/admin` (2)                                        |

Their inner paths must not collide: `/professor/sessions` comes from `session`, never
`/professor/professor/sessions`.

Two things follow:

- **Never mount the same `APIRouter` at two prefixes.** Paths inside it are
  relative to its own prefix, so mounting `student/router.py` at `/api/admin`
  would also expose `/api/admin/profile` and `/api/admin/schedule`. This is why
  student and professor each need a separate `admin_router.py` — their
  student-facing and admin-facing routes are distinct contracts.
- **A prefix may be shared; a router may not.** `dashboard` spans three mount points
  and therefore declares **three** routers in three modules
  (`student_router.py`, `professor_router.py`, `admin_router.py`) — never one router
  included three times.
- `features/enrollment/router.py` exists but is deliberately **not mounted**; do not
  wire it up.

---

### 6. Mount Router in `api/router.py`

```python
from features.program.router import router as program_router

# The prefix is already inside the router, so pass no prefix= here.
api_router.include_router(program_router)
```

**Done:**

- [ ] Imported the router object from the feature module
- [ ] `include_router` called with **no** `prefix=` argument
- [ ] Each `APIRouter` is mounted at exactly one prefix
- [ ] A feature spanning two prefixes exports a second router (see §5)

---

### 7. Backend Tests (`backend/src/tests/test_{feature}.py`)

> The backend suite is run with pytest. The `api-test` Compose service runs the suite in a one-shot container. Async tests need no `@pytest.mark.asyncio` decorator — `backend/pytest.ini` sets `asyncio_mode = auto`. The client fixture already exists; use it rather than declaring a local one.

```python
from sqlalchemy.ext.asyncio import AsyncSession

from features.program.service import ProgramService
from tests.conftest import Factories


async def test_create_program(api_client, auth_headers) -> None:
    # Collection routes are mounted without a trailing slash, so the real
    # path is /api/admin/programs, not /api/admin/programs/.
    headers = await auth_headers(role="admin")
    response = await api_client.post(
        "/api/admin/programs",
        json={"code": "BSCS", "name": "BS Computer Science", "total_years": 4},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["code"] == "BSCS"


async def test_program_service_requires_a_unique_code(
    test_db_session: AsyncSession, factories: Factories, settings
) -> None:
    """Service-level, when the route test is not enough.

    `factories` seeds via the same database the request path uses, and every
    keyword is a column override on top of a valid default.
    """

    await factories.program(code="BSCS")
    service = ProgramService(test_db_session)   # one arg: admin CRUD services
                                      # take no Settings
    # ...assert the domain exception is raised
```

**Available fixtures** (all in `src/tests/conftest.py`):

| Fixture | Use |
|---------|-----|
| `test_db_session` | `AsyncSession` on a per-test schema, rolled back at teardown |
| `test_client` | Sync `TestClient` for DB-free routing/auth checks |
| `api_client` | `httpx.AsyncClient` over the real app, wired to `test_db_session` |
| `auth_headers` | `await auth_headers(role=...)` → a real bearer header |
| `factories` | Seed users/programs/students/offerings/sessions/enrollments |
| `db_factory` | `await db_factory(Model, **columns)` escape hatch |
| `settings`, `now` | `Settings` for service construction; frozen UTC clock |

**Done:**

- [ ] Happy-path tests for each endpoint
- [ ] Edge cases tested (404, validation errors)
- [ ] Run: `docker compose -f docker-compose.dev.yml --profile test run --rm --build api-test` or `cd backend && python -m pytest src/tests/ -v`
- [ ] Lint and format: `cd backend && ruff check . && ruff format --check .`

---

### 8. Frontend Feature Slice

Create the feature directory under `src/lib/features/`. The files a slice actually needs
depend on what it does — treat the list below as the ceiling, not a checklist:

```
frontend/src/lib/features/{feature}/
├── store.svelte.ts    # Reactive state ($state runes)   — when the slice holds state
├── service.ts         # API calls                        — always
├── schema.ts          # Zod validators                   — when the slice validates input
├── mock.ts            # Fixture data for the mock leg    — when isMockMode() needs data
└── components/        # Svelte components                — when it renders any
```

Reality across the 13 existing slices: **every one has `service.ts`; only 1 has
`schema.ts` and 5 have `mock.ts`; `attendance` and `sync` are `service.ts` alone.**
Do not scaffold empty files to match a template — an unused `schema.ts` is dead weight,
and `notifications` has just `poll.ts` because polling is all it does.

**store.svelte.ts:**

```ts
// Runes mode is forced globally in vite.config.ts, so $state/$derived work in a
// plain .svelte.ts module. State lives in one exported $state object — a bare
// `let` is module-local and will not survive HMR or be shareable across importers.
import type { Program } from '$lib/shared/types';
import { listPrograms } from './service';

export const programState = $state<{ programs: Program[]; loading: boolean }>({
	programs: [],
	loading: false,
});

export async function loadPrograms(page = 1, size = 20): Promise<void> {
	programState.loading = true;
	try {
		const res = await listPrograms({ page, size });
		programState.programs = res.items;
	} finally {
		programState.loading = false;
	}
}
```

**service.ts:**

```ts
import { get, isMockMode, post } from '$lib/api/client';
import type { Paginated, Program } from '$lib/shared/types';
import { mockPrograms } from './mock';

// `isMockMode()` is the ONLY mock gate — it reads PUBLIC_MOCK_MODE, which
// api/client.ts:18 owns. Never branch on import.meta.env.DEV, on the presence of
// PUBLIC_API_URL, or on a service-local USE_MOCK flag: the API is real by default
// and mock mode is an explicit opt-in for UI work without a backend.
export async function listPrograms(params: {
	page: number;
	size: number;
}): Promise<Paginated<Program>> {
	if (isMockMode()) return mockPrograms(params);

	// Endpoint keys are EndpointDefs registered in api/endpoints.ts, not raw paths —
	// client.ts adds the /api prefix and handles auth, refresh and error envelopes.
	return await get<Paginated<Program>>('adminProgramList', params);
}

export async function createProgram(payload: Program): Promise<Program> {
	if (isMockMode()) return payload;
	return await post<Program>('adminProgramCreate', payload);
}
```

A local fixture fallback is fine and expected on the mock leg; what is not fine is
re-deciding *whether* to mock. `PUBLIC_API_URL` is optional and falls back to
`http://localhost:8000`, so keying off it would silently mock whenever the var is unset.

**Done:**

- [ ] Files created only where the slice needs them (not scaffolded empty)
- [ ] Components use runes syntax ($state, $derived, $effect, $props)
- [ ] Mock branching goes through `isMockMode()` and nothing else
- [ ] URLs referenced as `EndpointDef` keys from `api/endpoints.ts`
- [ ] Type check passes: `npm run check`

---

### 9. Wireframe & Documentation Updates

- Update `docs/design/wireframes.md` with new screens
- Update `docs/architecture/project-structure.md` with new feature folder
- Update `docs/architecture/api-contracts.md` with new endpoints
- Update `docs/architecture/data-flow.md` if new data flows exist

**Done:**

- [ ] Wireframes updated (route, screen number, description)
- [ ] Project structure tree updated
- [ ] API contracts updated
- [ ] Data flow diagrams updated (if applicable)

---

## Quick Reference: File Creation Order

```
1. model.py              → write model
2. alembic/env.py        → add import
3. alembic revision      → generate migration
4. alembic upgrade       → apply migration
5. schema.py             → write Pydantic schemas
6. service.py            → write business logic (flush, never commit)
7. router.py             → write endpoints, prefix baked in
8. api/router.py         → mount router (no prefix= argument)
9. tests                 → write tests (pytest; pytest.ini sets testpaths + asyncio_mode=auto)
10. frontend/            → feature slice
11. docs/                → update wireframes, contracts, structure
```

---

## Naming Conventions

| Item             | Convention                                                                                                                  | Example                                         |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| Feature folder   | lowercase, singular                                                                                                         | `program/`, `excuse/`, `analytics/`             |
| Model class      | PascalCase                                                                                                                  | `Program`, `YearLevel`, `ExcuseRequest`         |
| Table name       | snake_case, plural                                                                                                          | `programs`, `year_levels`, `excuse_requests`    |
| Schema class     | PascalCase + suffix                                                                                                         | `ProgramCreate`, `ProgramRead`, `ProgramUpdate` |
| Router prefix    | matches API contract, baked into the router; mounted with no `prefix=`                                                      | `/admin/programs`                               |
| Second prefix    | feature spans two mounts → second `APIRouter` in its own module (`admin_router.py`, `offering_router.py`)                    | `features/student/admin_router.py`              |
| Session dep      | `_get_db` (there is no public `get_db`)                                                                                     | `Depends(_get_db)`                              |
| Transactions     | `flush()` in services; the single `commit()` lives in `_get_db`                                                              | —                                               |
| Frontend store   | one `store.svelte.ts` per slice; `$state` runes inside                                                                   | `store.svelte.ts`                              |
| Frontend service | camelCase verbs, `const` arrow exports, no `fetch` outside the client                                                     | `listPrograms()`, `openSession()`              |
| Frontend schema  | Zod; `<scope><Entity><Action>Schema` + a PascalCase `…Input` inferred type                                              | `adminStudentCreateSchema`, `AdminStudentCreateInput` |

---

## Reference

- **Target schema:** `docs/design/database-er.md`
- **API endpoints:** `docs/architecture/api-contracts.md`
- **Migration strategy:** `docs/architecture/migration-strategy.md`
- **AGENTS.md conventions:** never commit `.env`, run alembic from `backend/`, imports in `alembic/env.py`
