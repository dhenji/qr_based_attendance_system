# Coding Standards — QR Attendance System

> Style and convention rules for backend (Python/FastAPI) and frontend (TypeScript/Svelte 5).
> Consistent with [AGENTS.md](../../AGENTS.md) conventions.

---

## Table of Contents

1. [Python (Backend)](#1-python-backend)
   1.1. [Style Guide](#11-style-guide)
   1.2. [Formatting Rules](#12-formatting-rules)
   1.3. [Function & Method Design](#13-function--method-design)
   1.4. [Import Order](#14-import-order)
   1.5. [Model Conventions](#15-model-conventions)
   1.6. [Schema Conventions (Pydantic)](#16-schema-conventions-pydantic)
   1.7. [Service Conventions](#17-service-conventions)
   1.8. [Router Conventions](#18-router-conventions)
   1.9. [Admin CRUD Slice Template](#19-admin-crud-slice-template)
2. [TypeScript / Svelte 5 (Frontend)](#2-typescript--svelte-5-frontend)
3. [Naming Conventions](#3-naming-conventions)
4. [Git & PR Conventions](#4-git--pr-conventions)
5. [Testing Standards](#5-testing-standards)

---

## 1. Python (Backend)

### 1.1 Style Guide

Follow **ruff** conventions. Ruff is **not yet installed** and there is currently no
linter, formatter, or CI enforced (per AGENTS.md). These are aspirational standards
to follow by convention until tooling is added:

- **Line length:** 88 characters (ruff default).
- **Quotes:** double quotes for strings.
- **Imports:** sorted by ruff rules — stdlib first, then third-party, then local. Put `from __future__ import annotations` at the top of every module.
- **Trailing commas:** yes on multi-line collections and function signatures.
- **Type hints:** required on all function signatures (args + return). Use `X | None` over `Optional[X]`.

### 1.2 Formatting Rules

| Rule                | Example                                                                                 |
| ------------------- | --------------------------------------------------------------------------------------- |
| Double quotes       | `"hello"` not `'hello'`                                                                 |
| f-strings preferred | `f"User {user.id}"` not `"User %s" % user.id`                                           |
| No wildcard imports | `from features.student.model import Student` not `from features.student.model import *` |
| Max line length 88  | Break long lines with parens or backslash                                               |
| Trailing commas     | `def foo(a, b,)` on multi-line signatures                                               |

### 1.3 Function & Method Design

- **Single responsibility**: Functions/methods should do one thing. If a function exceeds ~30 lines or has multiple logical steps, **extract helper functions** (private `_snake_case` methods or module-level functions).
- **Prefer `match` / dictionary dispatch over `if/elif/else` chains** when branching on a value:
  ```python
  # GOOD: dictionary dispatch
  _HANDLERS = {
      UserRole.STUDENT: _handle_student,
      UserRole.PROFESSOR: _handle_professor,
      UserRole.ADMIN: _handle_admin,
  }
  handler = _HANDLERS.get(role, _handle_default)
  return await handler(...)

  # GOOD: match (Python 3.10+)
  match role:
      case UserRole.STUDENT: return await _handle_student(...)
      case UserRole.PROFESSOR: return await _handle_professor(...)
      case _: return await _handle_default(...)

  # AVOID: long if/elif chains
  ```
- **Modern Python**: use `X | None` not `Optional[X]`, `list[T]` not `List[T]`, `dict[K, V]` not `Dict[K, V]`, `@dataclass`/`@dataclass(kw_only=True)` for data carriers, `from __future__ import annotations` at top of files.
- **Early returns / guard clauses** over nested blocks.
- **Private helpers** prefixed with `_` — module-level for pure logic, `self._method` for service-internal.
- **Extract shared logic to `shared/`**: If the same helper logic appears in **two or more feature modules**, move it to a module under `src/shared/` (e.g., `shared/validators.py`, `shared/utils.py`, `shared/csv_import.py`) and import it. Avoid copy-pasting logic across slices.
  - Examples already in codebase: `shared/csv_import.py` (parsing + email validation), `shared/validators.py`, `shared/enums.py`, `shared/pagination.py`, `shared/rate_limit.py`.
  - New shared helpers should be **pure functions** (no DB session) or **session-accepting functions** with clear signatures.
- **No inline magic values**: All field bounds, limits, thresholds, and config-like constants live in **`constants.py`** files:
  - Per-slice: `features/<slice>/constants.py` (e.g., `CODE_MAX_LENGTH`, `TOTAL_YEARS_MAX`)
  - Shared: `shared/pagination.py` (`DEFAULT_PAGE`, `MAX_PAGE_SIZE`, `SEARCH_MAX_LENGTH`)
  - Shared: `shared/enums.py` for `StrEnum` values
  - Auth-specific: `features/auth/constants.py` (`BACKUP_CODE_COUNT`, `SECURITY_QUESTION_POOL`, etc.)
- **`lambda` for tiny callbacks**: acceptable for one-liner key functions, `sorted(key=...)`, `filter()`, or simple `Callable` arguments — **not** for multi-line logic (extract a named function instead).
- **Generics for reusable algorithms**: when a helper operates on a type parameter, use **PEP 695** syntax (Python 3.12+):
  ```python
  def first_or_none[T](items: Sequence[T], predicate: Callable[[T], bool]) -> T | None:
      return next((item for item in items if predicate(item)), None)
  ```
  Avoid over-engineering — only when the same logic applies to multiple types in the codebase.

### 1.4 Import Order

```python
# 1. Standard library
from __future__ import annotations

from datetime import datetime, timezone

# 2. Third-party
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# 3. Local — core
from core.config import get_settings
from core.database import Base

# 4. Local — shared
from shared.enums import UserRole
from shared.mixins import TimestampMixin

# 5. Local — features
from features.student.model import Student
```

### 1.5 Model Conventions

- All models inherit from `Base` (imported from `core.database`).
- Use mixins (`CreatedAtMixin`, `TimestampMixin`) for timestamp columns.
- FK columns: `Mapped[int] = mapped_column(ForeignKey(...), nullable=False)`.
- Relationships: use `relationship()` with `back_populates` where bidirectional.
- Table names: lowercase, snake_case, plural (`students`, `attendance_records`).
- Unique constraints: define at column level or table level consistently.

### 1.6 Schema Conventions (Pydantic)

- Use **Pydantic v2** (`BaseModel` from `pydantic`).
- Request schemas: `FooCreate`, `FooUpdate`; read schemas: `FooRead` (e.g. `ProgramRead`, `StudentRead`). Legacy `FooResponse` names in `auth/schema.py` are kept as-is.
- Response models: use `model_config = ConfigDict(from_attributes=True)`.
- Never return ORM objects directly — serialize via response schema.
- Use `Annotated` with `Field()` for validation rules.
- **Field bounds come from the slice's `constants.py`**, never inline literals. Reuse the shared
  value if one exists (`NAME_MIN_LENGTH`, `NAME_MAX_LENGTH` in `features/admin/constants.py`;
  `MAX_PAGE_SIZE`, `SEARCH_MAX_LENGTH` in `shared/pagination.py`) instead of redeclaring it.
- **Input normalization is a `field_validator`**, not service logic: e.g. `ProgramCreate.code`
  strips whitespace and upper-cases, so the service compares one canonical form.
- **`FooUpdate` lists only the fields the contract's PATCH body accepts.** Immutable identity
  fields (`Program.code`, `Program.total_years`) are absent, not `Optional[...]`-ed.
- **Derived aggregates live on the read schema, defaulting to `0`** — `course_count`,
  `year_level_count`, `terms_count`, `enrolled_count`, `scan_count`. They are computed per
  request and are never model columns (see §1.9).
- **Nested reads get a `FooDetail(FooRead)`** that adds the child collection, e.g.
  `ProgramDetail.year_levels: list[YearLevelRead]`. A create response may reuse `FooRead`
  with the aggregates at their `0` default — correct for a brand-new row, and one model
  instead of two.

#### Exception Hierarchy Design (all feature `exceptions.py`)

Standard 3-tier pattern used by all 13 feature exception modules:

```python
class FeatureException(AppException):              # umbrella
    pass

class FeatureDomainException(FeatureException, DomainException):  # 422 base
    pass

class ConcreteNotFound(FeatureDomainException):     # 404
    status_code = 404
    code = "feature_not_found"
    def __init__(self, id: int): super().__init__(f"Feature {id} not found")

class ConcreteConflict(FeatureDomainException):     # 409
    status_code = 409
    code = "feature_conflict"
    def __init__(self, detail: str): super().__init__(detail)
```

- **Codes come from `api-contracts.md`** — never invent new ones
- 404 may fold ID into message; 409 reuses existing class names where contract overlaps (`EmailAlreadyExists`)

### 1.7 Service Conventions

- **CRUD slices under `/admin/*` are classes.** A slice whose job is create/read/update/archive
  for one or two models (`program`, `course`, student-admin, professor-admin) implements
  `features/<slice>/service.py` as `class <Feature>Service`, whose `__init__` takes the
  request `AsyncSession` and builds one `BaseCRUD` handle per model it touches. The router
  never constructs it: `api/deps.py` holds `_get_<feature>_service` plus the annotated
  `Annotated[<Feature>Service, Depends(_get_<feature>_service)]` alias
  (`<Feature>ServiceDep`), which receives `_get_db`, so the transaction boundary is unchanged.
  This is a standing rule, not a per-slice re-argument — see ADR-055 and ADR-058 in
  [decision-log.md](../project/decision-log.md).
- **A slice service is a `class <Feature>Service`.** All 15 `features/*/service.py` modules are
  classes; there is no module-level-function service module in the tree. Whether a class
  *earns* its place is the separate question below — the form is uniform, the justification
  varies per slice.
- **The class name carries the noun, so methods do not repeat it.** `create`, `get`, `list`,
  `archive`, `refresh_risk` — not `create_program`. Sub-resources extend the class:
  `list_years`, `create_year`.
- **Arguments after `self` are keyword-only**, and payloads arrive as the Create schema rather
  than as loose scalars.
- **Every list returns `PaginatedResponse[T]`** with an explicit `total` count and `page`/`size`
  bounds from `shared/pagination.py`. `BaseCRUD.list()` has its own `limit=50` default and is
  for internal lookups — do not return it from a list endpoint.
- **Optional filters go through `shared/query.apply_if(stmt, value, build)`**, which skips
  building a criterion for a `None` value; a bare `>=` comparison rejects `None` at
  construction time.
- **Return read schemas.** `model_validate` cannot see derived aggregates, so a response
  carrying counts or collections is built as `ProgramRead(**self._read_fields(row))`.
- **Sensitive mutations call `shared/audit.record_audit(...)`** in the caller's transaction, so
  the audit row rolls back with the change it describes.
- A service class must hold no state across requests; its `__init__` may only build
  per-request handles. Services call `BaseCRUD` for database operations.
- **Relationship access in async must be explicit.** `Program.year_levels` declares no
  `lazy=`, so reading `program.year_levels` after a query raises `MissingGreenlet`. Either
  pass `selectinload(Program.year_levels)` (or `joinedload`) in the query, or issue a second
  explicit query for the children — never read the attribute implicitly. Prefer the second
  query when the same children are also needed per row in `list`, so both paths share one
  helper.
- Business logic lives in services, not routers.
- **Services raise domain exceptions** from their `exceptions.py` — never `HTTPException`,
  never a raw `ValueError`. Only `AppException` subclasses reach the client's
  `{detail: {code, message}}` envelope (`DomainException` → 422, `DatabaseException` → 409).
  `HTTPException` is reserved for the auth layer in `api/deps.py`, which builds it through the
  `shared/dependencies.py` envelope helper.
- Transactions: flush within service methods; commit managed by the router/dependency.

#### Service Form Decision Tree (ADR-055/058/059/070)

| Slice                                                                            | Form                        | Why the class earns its place                                                                                               |
| -------------------------------------------------------------------------------- | --------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Admin CRUD (`/admin/*`: program, course, student-admin, professor-admin)           | **Class** (`FeatureService`) | Composes multiple `BaseCRUD` handles; per-request injection via `<Feature>ServiceDep` (ADR-058)                             |
| `admin`                                                                         | **Class** (`AdminService`)    | Composes 3 `BaseCRUD` handles (`User`, `Student`, `Professor`); accepted cost — ADR-055                  |
| `dashboard`                                                                       | **Class** (`DashboardService`) | Injects 5 sibling services (`student`, `attendance`, `session`, `analytics`, `reports`) — it aggregates features it does not own |
| `excuse`                                                                          | **Class** (`ExcuseService`)   | Composes 2 `BaseCRUD` handles (`ExcuseRequest`, `Attendance`)                                                               |
| `session`, `face_enrollment`, `auth`                                              | **Class**                    | Holds `Session` + `Settings` read by every method (ADR-059); `AuthService` also composes CRUDs + a rate limiter             |
| `system`, `attendance`                                                            | **Class**                    | Holds `Session` + `Settings` — the same shape as ADR-059's case                                                            |
| `analytics`, `reports`, `course_professor`                                        | **Class**                    | A cohesive operation set with private helper clusters; injected through the same seam (ADR-070)                             |

**Rule of thumb** (ADR-070): a class earns its place when `__init__` composes multiple
per-request handles (CRUD, settings, limiters) that every method uses — **or** when the service
exposes a cohesive operation set that would otherwise scatter across module-level functions and
lose the `*ServiceDep` seam. Composing handles is sufficient, not necessary. What does *not*
justify a class is a thin wrapper with nothing to compose and no meaningful seam; nothing in the
tree is one.

Everything not in the table is a **shared helper**, not a slice service —
`shared/csv_import.py` is module-level functions on purpose, has nothing to compose and needs no
seam, and is imported by three service modules and one admin router rather than injected.

### 1.8 Router Conventions

- **One `APIRouter` per (feature, mount point).** A router's prefix is its full
  contract path and is baked into the `APIRouter(...)`; `api/router.py` passes no
  `prefix=` argument. A feature whose endpoints span two prefixes declares a
  second `APIRouter` in its own module (e.g. `features/student/admin_router.py`
  at `/admin/students`, alongside `features/student/router.py` at `/student`).
  Several routers may share one mount point — `professor` and `session` both
  prefix `/professor`, `student` and `attendance` both prefix `/student` — so
  their inner paths must not collide. Never mount the same `APIRouter` twice:
  paths inside are relative to its prefix, so mounting `student/router.py` at
  `/api/admin` would also expose `/api/admin/profile`.
- **Collection routes are declared `""`, never `"/"`.** `@router.get("")` registers
  `/admin/programs` exactly; `"/"` adds a trailing-slash redirect the contract
  does not have.
- **The admin CRUD route set** is `GET ""`, `POST ""`, `GET /{id}`, `PATCH /{id}`,
  `DELETE /{id}` — in that order in the module, each with a one-line `summary=`.
- **Every admin route carries its own role guard**: a
  `_: Annotated[User, Depends(require_role(UserRole.ADMIN))]` parameter. `super_admin`
  passes automatically (`_role_matches` treats it as a superset of `admin`), so routes
  never need to name both roles.
- **Pagination is declared per route, not via a dependency**, so the bounds are visible
  in the OpenAPI schema: `page: int = Query(default=DEFAULT_PAGE, ge=1)` and
  `size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)`, with the
  constants coming from `shared/pagination.py`.
- **A list endpoint may add one optional filter the contract omits** — e.g. `?search=`
  (`ilike` across the human-readable columns) for a wireframe search box. It must stay
  optional, default to `None`, be length-capped by `SEARCH_MAX_LENGTH`, and be recorded
  in [api-contracts.md](../architecture/api-contracts.md) so the contract stays the
  source of truth. Adding a _required_ undocumented parameter is not allowed.
- **204 responses declare `status_code=status.HTTP_204_NO_CONTENT` and return `None`** —
  never a body, and never a status code the contract does not document.
- Mount all feature routers in `api/router.py`.
- Dependencies: `_get_db` for session (there is no public `get_db`), role-guard
  dependencies for authorization via `require_role(*UserRole)`, `<Feature>ServiceDep` for
  a class-based service.
- Use `response_model` on endpoint decorators (`PaginatedResponse[FooRead]` for lists).
- Paginated responses: `{items, total, page, size}`.

#### Mount Point Rules (ADR-057)

- **One `APIRouter` per (feature, mount point)** — prefix baked in `APIRouter(prefix="/admin/programs")`; `api/router.py` uses **no `prefix=`**
- **Shared mount points**: multiple routers → same prefix (`professor` + `session` → `/professor`; `student` + `attendance` → `/student`) — inner paths must not collide
- **Second router module** when a feature spans two prefixes: `admin_router.py`, `offering_router.py` — **never mount the same router twice**
- **Collection routes**: `@router.get("")` not `"/"` (avoids trailing-slash redirect)
- **Admin CRUD route order**: `GET ""`, `POST ""`, `GET /{id}`, `PATCH /{id}`, `DELETE /{id}` each with `summary=`

### 1.9 Admin CRUD Slice Template

A CRUD slice under `/api/admin/*` is exactly these files, beside the `model.py` that
already exists. `features/program/` is the reference implementation.

```
features/program/
  model.py         # already exists — Phase 3 adds NO migrations
  constants.py     # field bounds + re-used pagination bounds
  exceptions.py    # <Slice>Exception / <Slice>DomainException + concrete codes
  schema.py        # FooCreate, FooRead, FooUpdate (+ FooDetail when nested)
  service.py       # class FooService
  router.py        # APIRouter(prefix="/admin/<things>")
```

**`exceptions.py`** — one umbrella extending `AppException`, one `<Slice>DomainException`
extending it plus `DomainException` (422), then one class per documented code carrying
`status_code` and `code`, mirroring the shape in `features/admin/exceptions.py`. Codes come
from the contract (`409 program_code_exists`, `404 year_level_not_found`, …) and are never
invented. A 409 duplicates an existing class name (`EmailAlreadyExists`,
`OverlappingAssignmentException`); a 404 class may take the id and fold it into the message.

**`constants.py`** — the slice's own field bounds (`CODE_MAX_LENGTH` mirroring the column
`String(20)`, `TOTAL_YEARS_MAX`…); a bound that is not specific to the slice is imported
rather than restated. The list-query bounds live in `shared/pagination.py`:

```python
from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SEARCH_MAX_LENGTH,
)
```

`NAME_MIN_LENGTH` / `NAME_MAX_LENGTH` still come from `features/admin/constants.py`, which
re-exports the four `shared.pagination` names so the existing admin routes are unaffected.
That re-export is the temporary shape: if a third slice needs the name bounds, they get
their own `shared/constants.py` rather than a growing feature-to-feature import.

**`service.py` + `api/deps.py`** — see §1.7. `api/deps.py` is the only file outside the
slice folder that changes, and only additively:

```python
async def _get_program_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> ProgramService:
    return ProgramService(session)


ProgramServiceDep = Annotated[ProgramService, Depends(_get_program_service)]
```

**Derived aggregates are computed per request, in Python, one query per parent.** This is
an accepted N+1 at Phase 3 volumes (ADR-057 "Deferred"); do not build a grouped-JSONB
aggregate query or a materialised view yet, and never add the count as a column.

```python
terms_count = sum(len(yl.term_structure.get("terms") or []) for yl in program.year_levels)
```

Two traps this shape hides:

- `term_structure` is `{"terms": [{"code", "label"}]}`, so a bare `len(term_structure)`
  returns `1` per year level. Always read the `"terms"` key.
- `course_count` has **no** `courses.program_id` to count — D44 moved program FKs to
  `course_offerings`, so it is `COUNT(DISTINCT course_offerings.course_id)` restricted to
  the program (and to `is_active` offerings). There is no other path.

**Archive vs hard delete** — which route a slice gets is decided by the contract, not by
pattern-matching the other slices:

| Slice                                     | Soft archive                                        | Hard delete                                                        |
| ----------------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------ |
| programs, year levels, courses, offerings | `DELETE /{id}` → `is_active = False`                | none                                                               |
| students, professors                      | `PATCH /{id}` with `is_active` (archive/reactivate) | `DELETE /{id}/archive`, archived rows only, plus a has-records 409 |

- A soft archive touches **only its own row**. `DELETE /admin/programs/{id}` sets
  `programs.is_active = False` and nothing else: `year_levels` has no `is_active` column
  and `courses` is a decoupled template, so there is nothing to cascade to. Do not invent
  a cascade, and do not re-activate archived offerings as a side effect.
- Reactivation is the same `PATCH` with `is_active: true`; slices that have no `DELETE
/{id}` reach `archive()`/`reactivate()` from the PATCH handler.
- The hard delete needs **two** guards, not one: `is_active = False` (else
  `409 not_archived`) _and_ a child-row check (`409 student_has_records` /
  `professor_has_records`), because `enrollments`, `attendance_records` and
  `excuse_requests` reference `students.id` with `ondelete="RESTRICT"` (and `sessions`
  references `professors.id`). The FKs stay RESTRICT as the last line of defence — never
  relax them to CASCADE to make the delete succeed.
- A slice that documents no delete route gets none. Adding `DELETE /{id}` "to match the
  pattern" creates an undocumented surface.

**A slice is not mounted when it is written.** `api/router.py` is edited once,
by the session that owns the whole mount list (the mount session). Until then, verify a new router
by importing it and reading `router.routes`, and never add an `include_router` call in the
slice's own session.

#### Dependency Injection Patterns

- **Service deps** in `api/deps.py`:
  ```python
  async def _get_program_service(
      session: Annotated[AsyncSession, Depends(_get_db)],
  ) -> ProgramService:
      return ProgramService(session)

  ProgramServiceDep = Annotated[ProgramService, Depends(_get_program_service)]
  ```
- **Settings injection**:
  - Admin CRUD services: **not injected** (don't need settings)
  - `AuthService`, `FaceEnrollmentService`, `SessionService`, `SystemService`, `AttendanceService`:
    `Settings` via `__init__(session, settings: Settings | None = None)` with `settings or get_settings()`
- **Transaction boundary**: single `commit()` in `_get_db`; services only `flush()`

---

## 2. TypeScript / Svelte 5 (Frontend)

### 2.1 Runes Mode (Required)

Svelte 5 runes are **forced on** via `vite.config.ts`. Write all reactive code using runes:

```svelte
<!-- CORRECT: Runes mode -->
<script lang="ts">
  let count = $state(0);
  let doubled = $derived(count * 2);

  function increment() {
    count++;
  }
</script>

<!-- WRONG: Legacy reactive declarations -->
<script lang="ts">
  let count = 0;          // <-- legacy, will not compile in runes mode
  $: doubled = count * 2; // <-- legacy
</script>
```

### 2.2 Rune Reference

| Rune        | Purpose           | Example                                   |
| ----------- | ----------------- | ----------------------------------------- |
| `$state`    | Reactive variable | `let name = $state('')`                   |
| `$derived`  | Computed value    | `let full = $derived(first + ' ' + last)` |
| `$effect`   | Side effect       | `$effect(() => { ... })`                  |
| `$props`    | Component props   | `let { title, onAction } = $props()`      |
| `$bindable` | Two-way binding   | `let { value = $bindable() } = $props()`  |
| `$inspect`  | Debug logging     | `$inspect(count)`                         |

### 2.3 TypeScript Conventions

- **Strict mode** enabled (`tsconfig.json`).
- Use `interface` for object shapes, `type` for unions/intersections.
- Prefix component props interfaces with the component name: `SessionCardProps`.
- **Shared constants are `as const` objects plus a derived union, never `enum`.** There is no
  `export enum` in `frontend/src`; `lib/shared/constants/roles.ts:3-10` is the reference shape:
  ```ts
  export const Roles = {
    SUPER_ADMIN: 'super_admin' as const,
    ADMIN: 'admin' as const,
    PROFESSOR: 'professor' as const,
    STUDENT: 'student' as const,
  };

  export type UserRole = keyof typeof Roles;
  ```
  A string-literal union keeps the values assignable to the backend's `StrEnum` members and
  avoids the nominal typing an `enum` introduces. Python side, use `StrEnum` in
  `shared/enums.py`.
- Zod schemas for API request/response validation (live in the feature's `schema.ts`).

### 2.4 Svelte Component Conventions

- One component per file, PascalCase filename: `Step1SessionEntry.svelte`.
- `<script lang="ts">` always.
- Props via `$props()` rune.
- Events: use callback props (`onAction`), not `createEventDispatcher`.
- Slots: use `{@render children()}` (Svelte 5 snippet API), not `<slot>`.
- CSS: scoped by default; use `:global()` only when necessary.

### 2.5 File Organization (Feature Slices)

Each feature under `src/lib/features/<name>/`. **The file set is per-slice, not a
template** — scaffold only what the slice needs, since an unused `schema.ts` is dead weight:

```
features/
  student/
    store.svelte.ts      # Reactive state ($state object store)
    face.svelte.ts       # Face-enrollment state, kept separate per concern
    service.ts           # API communication
    components/          # UI components
      StudentCard.svelte
      StudentList.svelte
  auth/
    service.ts           # + tokens.ts, errors.ts, security.ts
    store.svelte.ts
    mock.ts
  notifications/
    poll.ts              # nothing else — polling is all it does
```

Measured across the 13 slices: **`service.ts` is universal** (13/13); `store.svelte.ts` 5/13;
`mock.ts` 5/13; `components/` 4/13; `schema.ts` **1/13**. `attendance` and `sync` are
`service.ts` alone. So "which files does a feature slice have" is answered per feature, not
from a checklist.

Filenames are **unprefixed** — the directory already namespaces the slice, so it is
`store.svelte.ts`, `service.ts`, `schema.ts`, never `studentService.ts`.

### 2.6 Import Paths

- Use `$lib` alias for shared code: `import { get } from '$lib/api/client'`.
- Feature imports: `import { StudentCard } from '$lib/features/student/components'`.
- Never use relative paths going more than two levels up.

---

## 3. Naming Conventions

### 3.1 Backend

| Element         | Convention                                        | Example                                 |
| --------------- | ------------------------------------------------- | --------------------------------------- |
| Tables          | lowercase, snake_case, plural                     | `students`, `attendance_records`        |
| Columns         | snake_case                                        | `student_id`, `created_at`              |
| Models          | PascalCase                                        | `Student`, `Attendance`                    |
| Schemas         | PascalCase + suffix                               | `StudentCreate`, `SessionResponse`      |
| Services        | PascalCase + suffix (admin CRUD)                  | `ProgramService`                        |
| Service methods | snake_case, keyword-only after `self`, noun not repeated | `create()`, `get()`, `list()`         |
| Routers         | snake_case, prefix baked in                       | `student_router`, `session_router`      |
| Router modules  | snake_case, one per mount point                   | `admin_router.py`, `offering_router.py` |
| Service deps    | `<Feature>ServiceDep` in `api/deps.py`            | `ProgramServiceDep`                     |
| Exceptions      | `<Feature>Exception` / `<Feature>DomainException` | `ProgramCodeExistsException`            |
| Slice constants | UPPER_SNAKE in `<slice>/constants.py`             | `MAX_PAGE_SIZE`                         |
| Functions       | snake_case                                        | `get_student_by_id()`                   |
| Constants       | UPPER_SNAKE_CASE                                  | `FACE_MATCH_THRESHOLD`                  |
| Enums           | PascalCase class, UPPER_SNAKE values              | `UserRole.STUDENT`                      |
| Env vars        | UPPER_SNAKE_CASE                                  | `DATABASE_URL`, `HMAC_SECRET_KEY`       |

### 3.2 Frontend

| Element          | Convention            | Example                           |
| ---------------- | --------------------- | --------------------------------- |
| Components       | PascalCase            | `SessionCard.svelte`              |
| Component files  | PascalCase.svelte     | `Step1SessionEntry.svelte`        |
| Stores           | one per slice, unprefixed          | `store.svelte.ts`                  |
| Services         | unprefixed                         | `service.ts`                       |
| Schemas          | unprefixed                         | `schema.ts`                        |
| Types/Interfaces | PascalCase            | `StudentProfile`, `SessionConfig` |
| Functions        | camelCase             | `formatDate()`                    |
| CSS classes      | kebab-case            | `scan-progress`, `status-badge`   |
| Routes           | lowercase, kebab-case | `/student/scan`                   |
| Env vars         | PUBLIC_ prefix        | `PUBLIC_API_URL`                  |

---

## 4. Git & PR Conventions

### 4.1 Branch Naming

| Type     | Pattern                 | Example                     |
| -------- | ----------------------- | --------------------------- |
| Feature  | `feature/<short-name>`  | `feature/student-scan-flow` |
| Fix      | `fix/<short-name>`      | `fix/session-expiry-calc`   |
| Docs     | `docs/<short-name>`     | `docs/refactor`             |
| Refactor | `refactor/<short-name>` | `refactor/excuse-service`   |

### 4.2 Commit Messages

Format: `<type>(<scope>): <description>`

Types:

- `feat` — new feature
- `fix` — bug fix
- `docs` — documentation only
- `refactor` — code change that neither fixes a bug nor adds a feature
- `test` — adding or updating tests
- `chore` — maintenance (deps, CI, config)

Examples:

```
feat(session): add dual-timer active session view
fix(attendance): correct expiry calculation for late window
docs(api): update excuse endpoint contracts
refactor(program): extract term structure validation
```

Scope is optional but recommended: `auth`, `student`, `session`, `attendance`, `program`, `analytics`, `excuse`, `system`, `frontend`, `db`.

### 4.3 Pull Request Rules

- **One feature/fix per PR.** Keep PRs focused.
- PR title matches commit message style: `<type>(<scope>): <description>`.
- PR description must include:
  - What changed and why
  - Which decision IDs from the Decision Log are addressed (if applicable)
  - How to test manually
- No secrets, keys, or `.env` files in commits.
- All `npm run check` must pass before merging (frontend changes).
- Branch off `main`; merge via PR review.
- Squash-merge preferred for clean history.

### 4.4 .gitignore Rules

- Never commit `.env` or `.env.*` (except `.env.example` and `.env.test`).
- Never commit `__pycache__/`, `.venv/`, `node_modules/`, `.svelte-kit/`.
- Backend-only artifacts — Python bytecode, `.venv/`, pytest/coverage output, and `backups/` — are ignored by `backend/.gitignore`.
- Env-file rules stay in the root `.gitignore`: `frontend/.env` is also a real file. A nested `.gitignore` takes precedence rather than merging, so duplicating them would mean two files that must stay byte-identical.

---

## 5. Testing Standards

### 5.1 Backend Tests

- **Framework:** pytest + pytest-asyncio (`backend/requirements.txt`); config in `backend/pytest.ini`.
- **Location:** `backend/src/tests/`.
- **Naming:** `test_<feature>_<scenario>.py`.
- **Fixtures:** use `conftest.py` for shared fixtures (test DB session, test client, factories).
- **Async tests:** `asyncio_mode = auto`, so no `@pytest.mark.asyncio` decorator is needed. The pre-existing sync tests that call `asyncio.run()` keep working untouched.
- **Test database:** in-memory SQLite by default; set `TEST_DATABASE_URL` to run the same suite against Postgres.
- **No coverage threshold is enforced.** `--cov` is deliberately absent from `pytest.ini`'s
  `addopts`, so nothing fails a drop in coverage. Treat coverage as a review signal, not a gate.

### 5.2 Frontend Tests

- **Type checking:** `npm run check` (svelte-check) must pass.
- **Component testing:** Vitest + @testing-library/svelte (to be added).
- **Naming:** `<ComponentName>.test.ts` co-located with component.
- **E2E (later):** Playwright for critical user flows.

### 5.3 Test Data

See [test-data.md](../testing/test-data.md) for seed specifications:

- 42 students at the `small` scale (`SCALE_COUNTS` in `src/tests/seed_data.py`), across cohorts sharing a GE course
- Professors including one effective-dated handover
- 6 weeks of historical attendance

> **Note:** the seed **does** create the programs and year levels it needs, get-or-create style
> (`seed_data.py:201,236-246`), so it is self-contained. It also seeds sessions, attendance,
> excuse requests, staged and promoted risk scores, and pending sync rows — see
> [test-data.md](../testing/test-data.md) for the per-scale row counts.

---

## 6. Environment Variables

### 6.1 Backend

All backend env vars are documented in [backend-setup.md](./backend-setup.md), [production-checklist.md §1](../deployment/production-checklist.md), and `backend/.env.example`.

Rules:

- Never hardcode secrets — always use env vars.
- `JWT_SECRET` required when `DEBUG=false` (validated in `config.py`).
- `BACKUP_ENCRYPTION_KEY` must be `openssl rand -base64 32`.
- New env vars must be added to `.env.example` with comments.

### 6.2 Frontend

Only `PUBLIC_*` variables reach the browser. All others are server-side only.

```bash
PUBLIC_API_URL=http://localhost:8000   # optional — client.ts falls back to this exact value
PUBLIC_MOCK_MODE=true                  # optional — the one mock gate; default is the real API
```

---

## 7. Documentation Standards

- All new docs go in the appropriate `docs/` subdirectory.
- Cross-reference other docs with relative links: `[API Contracts](../architecture/api-contracts.md)`.
- Reference Decision Log IDs when citing decisions: `(D12)`.
- Wireframes use ASCII boxes, 700x520 canvas, conventions from §9 of the Refactor Plan.
- Screenshots in user guides use `[FIG: description]` placeholders.
- Every glossary term links to `docs/project/glossary.md`.
