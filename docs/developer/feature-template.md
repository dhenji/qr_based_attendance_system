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

Plus an Alembic migration, backend tests, and frontend feature slice.

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


class YearLevel(TimestampMixin, Base):
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
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    program: Mapped["Program"] = relationship(back_populates="year_levels")
```

**Conventions:**
- Use `BigInteger` for PKs and FKs
- Use `Mapped[type]` with `mapped_column()` (SQLAlchemy 2.0 style)
- Inherit `TimestampMixin` from `shared/mixins.py` for `created_at`/`updated_at`
- Use `String(n)` for bounded strings, `Text` for unbounded
- FK `ondelete` rule: `CASCADE` for owned children, `RESTRICT` for references
- Import `Base` from `core.database`

**Done:**
- [ ] Model class defined with correct `__tablename__`
- [ ] PK, columns, FKs match target schema (§6 of DOCS_REFACTOR_PLAN.md)
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
    await session.commit()
    await session.refresh(program)
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
- `session.commit()` + `session.refresh()` after writes
- Raise domain exceptions (not HTTP exceptions) for business rule violations
- Keep functions focused — one operation per function

**Done:**
- [ ] CRUD operations implemented
- [ ] Business rules enforced (not in router)
- [ ] Database session passed as parameter (not global)

---

### 5. Router (`backend/src/features/{feature}/router.py`)

FastAPI router with endpoint definitions.

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from features.program.schema import ProgramCreate, ProgramRead
from features.program import service

router = APIRouter(prefix="/admin/programs", tags=["programs"])


@router.post("/", response_model=ProgramRead)
async def create_program(
    payload: ProgramCreate,
    session: AsyncSession = Depends(get_db),
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
    session: AsyncSession = Depends(get_db),
) -> list[ProgramRead]:
    programs = await service.list_programs(session)
    return [ProgramRead.model_validate(p) for p in programs]


@router.get("/{program_id}", response_model=ProgramRead)
async def get_program(
    program_id: int,
    session: AsyncSession = Depends(get_db),
) -> ProgramRead:
    program = await service.get_program(session, program_id)
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")
    return ProgramRead.model_validate(program)
```

**Conventions:**
- Prefix matches API contract (§7 of DOCS_REFACTOR_PLAN.md)
- `Depends(get_db)` for session injection
- Response model is the Read schema
- Errors: `HTTPException` with appropriate status codes
- Tags group endpoints in Swagger UI

**Done:**
- [ ] Endpoints match §7 API inventory
- [ ] Request/response schemas used correctly
- [ ] Error responses consistent (`{detail: {code, message}}`)

---

### 6. Mount Router in `api/router.py`

```python
from features.program.router import router as program_router

# Add alongside existing router includes:
api_router.include_router(program_router)
```

---

### 7. Backend Tests (`backend/src/tests/test_{feature}.py`)

```python
import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_create_program(client):
    response = await client.post("/admin/programs/", json={
        "code": "BSCS",
        "name": "Bachelor of Science in Computer Science",
        "total_years": 4,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "BSCS"
    assert data["total_years"] == 4


@pytest.mark.asyncio
async def test_list_programs(client):
    response = await client.get("/admin/programs/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

**Done:**
- [ ] Happy-path tests for each endpoint
- [ ] Edge cases tested (404, validation errors)
- [ ] Run: `cd backend && python -m pytest src/tests/ -v`

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
import type { Program } from './schema';

let programs = $state<Program[]>([]);
let loading = $state(false);

export function getPrograms() {
    return { get programs() { return programs; }, loading };
}
```

**service.ts:**

```ts
import { PUBLIC_API_URL } from '$env/static/public';
import { mockPrograms } from './mock';

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
6. service.py            → write business logic
7. router.py             → write endpoints
8. api/router.py         → mount router
9. tests                 → write tests
10. frontend/            → feature slice
11. docs/                → update wireframes, contracts, structure
```

---

## Naming Conventions

| Item | Convention | Example |
|------|-----------|---------|
| Feature folder | lowercase, singular | `program/`, `excuse/`, `analytics/` |
| Model class | PascalCase | `Program`, `YearLevel`, `ExcuseRequest` |
| Table name | snake_case, plural | `programs`, `year_levels`, `excuse_requests` |
| Schema class | PascalCase + suffix | `ProgramCreate`, `ProgramRead`, `ProgramUpdate` |
| Router prefix | matches API contract | `/admin/programs` |
| Frontend store | `$state` in `.svelte.ts` | `programs.svelte.ts` |
| Frontend service | camelCase functions | `fetchPrograms()`, `createProgram()` |
| Frontend schema | Zod | `programSchema`, `programCreateSchema` |

---

## Reference

- **Target schema:** `DOCS_REFACTOR_PLAN.md` §6
- **API endpoints:** `DOCS_REFACTOR_PLAN.md` §7
- **Migration strategy:** `docs/architecture/migration-strategy.md`
- **AGENTS.md conventions:** never commit `.env`, run alembic from `backend/`, imports in `alembic/env.py`
