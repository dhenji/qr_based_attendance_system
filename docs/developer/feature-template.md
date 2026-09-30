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

Plus an Alembic migration, frontend feature slice, and (aspirational) backend tests.

---

## Checklist

### 1. Model (`backend/src/features/{feature}/model.py`)

Define SQLAlchemy ORM models inheriting from `core.database.Base`.

**Worked example — `program/model.py`:**

```python
from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
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
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")

    year_levels: Mapped[list["YearLevel"]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )


class YearLevel(Base):
    __tablename__ = "year_levels"
    __table_args__ = (
        UniqueConstraint("program_id", "year_number", name="uq_program_year"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    program_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("programs.id", ondelete="CASCADE")
    )
    year_number: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(50))
    term_structure: Mapped[dict] = mapped_column(JSONB)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))

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
from pydantic import BaseModel, Field


class ProgramCreate(BaseModel):
    code: str = Field(..., max_length=20)
    name: str = Field(..., max_length=100)
    description: str | None = None
    total_years: int = Field(..., ge=1, le=6)


class ProgramRead(BaseModel):
    id: int
    code: str
    name: str
    description: str | None
    total_years: int
    is_active: bool

    model_config = {"from_attributes": True}


class ProgramUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    total_years: int | None = Field(None, ge=1, le=6)
```

**Conventions:**

- Separate `Create`, `Read`, `Update` schemas per entity
- `Read` uses `from_attributes = True` for ORM compatibility
- Use `Field(...)` for constraints (`ge`, `le`, `max_length`)
- Never return passwords or secrets in `Read` schemas

**Done:**

- [ ] Create/Read/Update schemas defined
- [ ] Field constraints match business rules
- [ ] No sensitive data exposed in Read schema

---

### 4. Service (`backend/src/features/{feature}/service.py`)

Business logic layer. No HTTP concerns — receives/returns domain objects.

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from features.program.model import Program


async def create_program(session: AsyncSession, *, code: str, name: str,
                         total_years: int) -> Program:
    program = Program(code=code, name=name, total_years=total_years)
    session.add(program)
    await session.flush()

    return program


async def get_program(session: AsyncSession, program_id: int) -> Program | None:
    result = await session.execute(select(Program).where(Program.id == program_id))
    return result.scalar_one_or_none()


async def list_programs(session: AsyncSession) -> list[Program]:
    result = await session.execute(select(Program).where(Program.is_active == True))
    return list(result.scalars().all())
```

**Conventions:**

- Functions are `async`, receive `AsyncSession` as first param
- Use `select()` + `where()` (SQLAlchemy 2.0 query style)
- **`await session.flush()` after writes — never `commit()` and never `refresh()`**
- Raise domain exceptions (not HTTP exceptions) for business rule violations
- Keep functions focused — one operation per function

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

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import _get_db, require_role
from features.program.schema import ProgramCreate, ProgramRead
from features.program import service
from shared.enums import UserRole

# The full contract path lives here, not in api/router.py.
router = APIRouter(prefix="/admin/programs", tags=["programs"])


@router.post("/", response_model=ProgramRead)
async def create_program(
    payload: ProgramCreate,
    _admin: Annotated[object, Depends(require_role(UserRole.ADMIN))],
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> ProgramRead:
    program = await service.create_program(
        session,
        code=payload.code,
        name=payload.name,
        total_years=payload.total_years,
    )
    return ProgramRead.model_validate(program)


@router.get("/", response_model=list[ProgramRead])
async def list_programs(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> list[ProgramRead]:
    programs = await service.list_programs(session)
    return [ProgramRead.model_validate(p) for p in programs]


@router.get("/{program_id}", response_model=ProgramRead)
async def get_program(
    program_id: int,
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> ProgramRead:
    program = await service.get_program(session, program_id)
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")
    return ProgramRead.model_validate(program)
```

**Conventions:**

- Prefix matches [API contract](../architecture/api-contracts.md) and is **baked
  into the router**; `api/router.py` must not pass a `prefix=` argument
- The session dependency is **`_get_db`** — there is no public `get_db`
- `Depends(_get_db)` for session injection
- Response model is the Read schema
- Errors: `HTTPException` with appropriate status codes
- Tags group endpoints in Swagger UI

**Done:**

- [ ] Endpoints match §7 API inventory
- [ ] Request/response schemas used correctly
- [ ] Error responses consistent (`{detail: {code, message}}`)

#### One `APIRouter` per (feature, mount point)

A router's prefix is its full contract path, so **one `APIRouter` serves exactly
one mount point**. Most features need only one router. When a single feature's
endpoints span two prefixes, declare a **second `APIRouter` in its own module**
rather than mounting the same router twice:

| Feature module | Router prefix | Mounted at |
| --- | --- | --- |
| `features/auth/router.py` | `/auth` | `/api/auth` |
| `features/admin/router.py` | `/admin/users` | `/api/admin/users` |
| `features/course/router.py` | `/admin/courses` | `/api/admin/courses` |
| `features/course/offering_router.py` | `/admin/offerings` | `/api/admin/offerings` |
| `features/student/router.py` | `/student` | `/api/student` |
| `features/student/admin_router.py` | `/admin/students` | `/api/admin/students` |
| `features/attendance/router.py` | `/student` | `/api/student` |
| `features/attendance/admin_router.py` | `/admin/attendance` | `/api/admin/attendance` |
| `features/professor/router.py` | `/professor` | `/api/professor` |
| `features/session/router.py` | `/professor` | `/api/professor` |
| `features/professor/admin_router.py` | `/admin/professors` | `/api/admin/professors` |

Two things follow from the table:

- **Several routers may share one mount point.** `professor` and `session` both
  prefix `/professor`, and `student` and `attendance` both prefix `/student` — a
  mount point is a namespace, not an owner. Their route paths inside the shared
  prefix must not collide (`/professor/sessions` from `session`, not
  `/professor/professor/sessions`).
- **Never mount the same `APIRouter` at two prefixes.** Paths inside it are
  relative to its own prefix, so mounting `student/router.py` at `/api/admin`
  would also expose `/api/admin/profile` and `/api/admin/schedule`. This is why
  student and professor each need a separate `admin_router.py` — their
  student-facing and admin-facing routes are distinct contracts.

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
    service = ProgramService(test_db_session, settings)
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

---

### 8. Frontend Feature Slice

Create the feature directory under `src/lib/features/`:

```
frontend/src/lib/features/{feature}/
├── store.svelte.ts    # Reactive state ($state runes)
├── service.ts         # API calls (with mock fallback)
├── schema.ts          # Zod validation schemas
├── mock.ts            # Mock data for dev
└── components/        # Svelte components
```

**store.svelte.ts:**

```ts
// Use $state runes in a .svelte.ts file (runes mode is forced globally):
import type { Program } from "./schema";

let programs = $state<Program[]>([]);
let loading = $state(false);

export function getPrograms() {
  return {
    get programs() {
      return programs;
    },
    loading,
  };
}
```

**service.ts:**

```ts
import { PUBLIC_API_URL } from "$env/static/public";
import { mockPrograms } from "./mock";

const USE_MOCK = import.meta.env.DEV && !PUBLIC_API_URL;

export async function fetchPrograms() {
  if (USE_MOCK) return mockPrograms;
  const res = await fetch(`${PUBLIC_API_URL}/admin/programs`);
  return res.json();
}
```

**Done:**

- [ ] Store, service, schema, mock files created
- [ ] Components use runes syntax ($state, $derived, $effect, $props)
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
9. tests                 → write tests (aspirational — no test runner yet)
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
| Frontend store   | `$state` in `.svelte.ts`                                                                                                    | `programs.svelte.ts`                            |
| Frontend service | camelCase functions                                                                                                         | `fetchPrograms()`, `createProgram()`            |
| Frontend schema  | Zod                                                                                                                         | `programSchema`, `programCreateSchema`          |

---

## Reference

- **Target schema:** `docs/design/database-er.md`
- **API endpoints:** `docs/architecture/api-contracts.md`
- **Migration strategy:** `docs/architecture/migration-strategy.md`
- **AGENTS.md conventions:** never commit `.env`, run alembic from `backend/`, imports in `alembic/env.py`
