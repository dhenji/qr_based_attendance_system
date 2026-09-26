# Coding Standards — QR Attendance System

> Style and convention rules for backend (Python/FastAPI) and frontend (TypeScript/Svelte 5).
> Consistent with [AGENTS.md](../../AGENTS.md) conventions.

---

## Table of Contents

1. [Python (Backend)](#1-python-backend)
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
- **Imports:** sorted by ruff rules — stdlib first, then third-party, then local. Use `from __future__ import annotations` where helpful.
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

### 1.3 Import Order

```python
# 1. Standard library
from datetime import datetime, timezone
from typing import Optional

# 2. Third-party
from fastapi import APIRouter, Depends, HTTPException
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

### 1.4 Model Conventions

- All models inherit from `Base` (imported from `core.database`).
- Use mixins (`CreatedAtMixin`, `TimestampMixin`) for timestamp columns.
- FK columns: `Mapped[int] = mapped_column(ForeignKey(...), nullable=False)`.
- Relationships: use `relationship()` with `back_populates` where bidirectional.
- Table names: lowercase, snake_case, plural (`students`, `attendance_records`).
- Unique constraints: define at column level or table level consistently.

### 1.5 Schema Conventions (Pydantic)

- Use **Pydantic v2** (`BaseModel` from `pydantic`).
- Request schemas: `FooCreate`, `FooUpdate`; read schemas: `FooRead` (e.g. `ProgramRead`, `StudentRead`). Legacy `FooResponse` names in `auth/schema.py` are kept as-is.
- Response models: use `model_config = ConfigDict(from_attributes=True)`.
- Never return ORM objects directly — serialize via response schema.
- Use `Annotated` with `Field()` for validation rules.

### 1.6 Service Conventions

- Services are **module-level async functions**: `async def create_foo(session: AsyncSession, ...)`.
- **No service classes by default** — with one sanctioned exception: a service may be a
  class when `__init__` builds per-request collaborators that every method would
  otherwise re-derive (composed `BaseCRUD` handles, settings, rate limiters).
  `AuthService` (5 `BaseCRUD` handles + settings) and `AdminService` (3 handles)
  are the clear cases; `CourseProfessorService` is retained as a borderline one
  that would not justify a new sibling. A session alone does **not** qualify —
  prefer a function for a new single-method service. See ADR-055 in
  [decision-log.md](../project/decision-log.md).
- A service class must hold no state across requests; its `__init__` may only
  build per-request handles.
- Business logic lives in services, not routers.
- Services call `BaseCRUD` for database operations.
- Raise `HTTPException` or domain exceptions, never raw `ValueError`.
- Transactions: flush within service methods; commit managed by the router/dependency.

### 1.7 Router Conventions

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
- Mount all feature routers in `api/router.py`.
- Dependencies: `_get_db` for session (there is no public `get_db`), role-guard
  dependencies for authorization via `require_role(*UserRole)`.
- Use `response_model` on endpoint decorators.
- Paginated responses: `{items, total, page, size}`.

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
- Use `enum` for role/status constants shared across features.
- Zod schemas for API request/response validation (live in the feature's `schema.ts`).

### 2.4 Svelte Component Conventions

- One component per file, PascalCase filename: `Step1SessionEntry.svelte`.
- `<script lang="ts">` always.
- Props via `$props()` rune.
- Events: use callback props (`onAction`), not `createEventDispatcher`.
- Slots: use `{@render children()}` (Svelte 5 snippet API), not `<slot>`.
- CSS: scoped by default; use `:global()` only when necessary.

### 2.5 File Organization (Feature Slices)

Each feature under `src/lib/features/<name>/`:

```
features/
  student/
    store.svelte.ts      # Reactive state (Svelte 5 runes)
    service.ts           # API communication
    schema.ts            # Zod validators
    mock.ts              # Mock data for dev
    components/          # UI components
      StudentCard.svelte
      StudentList.svelte
```

### 2.6 Import Paths

- Use `$lib` alias for shared code: `import { get } from '$lib/api/client'`.
- Feature imports: `import { StudentCard } from '$lib/features/student/components'`.
- Never use relative paths going more than two levels up.

---

## 3. Naming Conventions

### 3.1 Backend

| Element   | Convention                           | Example                            |
| --------- | ------------------------------------ | ---------------------------------- |
| Tables    | lowercase, snake_case, plural        | `students`, `attendance_records`   |
| Columns   | snake_case                           | `student_id`, `created_at`         |
| Models    | PascalCase                           | `Student`, `AttendanceRecord`      |
| Schemas   | PascalCase + suffix                  | `StudentCreate`, `SessionResponse` |
| Services  | PascalCase + suffix                  | `StudentService`, `SessionService` |
| Routers   | snake_case                           | `student_router`, `session_router` |
| Functions | snake_case                           | `get_student_by_id()`              |
| Constants | UPPER_SNAKE_CASE                     | `FACE_MATCH_THRESHOLD`             |
| Enums     | PascalCase class, UPPER_SNAKE values | `UserRole.STUDENT`                 |
| Env vars  | UPPER_SNAKE_CASE                     | `DATABASE_URL`, `HMAC_SECRET_KEY`  |

### 3.2 Frontend

| Element          | Convention            | Example                           |
| ---------------- | --------------------- | --------------------------------- |
| Components       | PascalCase            | `SessionCard.svelte`              |
| Component files  | PascalCase.svelte     | `Step1SessionEntry.svelte`        |
| Stores           | camelCase             | `authStore.svelte.ts`             |
| Services         | camelCase             | `studentService.ts`               |
| Schemas          | camelCase             | `studentSchema.ts`                |
| Types/Interfaces | PascalCase            | `StudentProfile`, `SessionConfig` |
| Functions        | camelCase             | `formatDate()`                    |
| CSS classes      | kebab-case            | `scan-progress`, `status-badge`   |
| Routes           | lowercase, kebab-case | `/student/scan/step/1`            |
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
- Backups directory (`backups/`) is gitignored.

---

## 5. Testing Standards

### 5.1 Backend Tests

- **Framework:** pytest + pytest-asyncio (to be added to `requirements.txt`).
- **Location:** `backend/src/tests/`.
- **Naming:** `test_<feature>_<scenario>.py`.
- **Fixtures:** use `conftest.py` for shared fixtures (test DB session, test client).
- **Async tests:** all DB-dependent tests use `@pytest.mark.asyncio`.
- **Coverage target:** 80%+ for services, 100% for critical paths (attendance validation, session expiry).

### 5.2 Frontend Tests

- **Type checking:** `npm run check` (svelte-check) must pass.
- **Component testing:** Vitest + @testing-library/svelte (to be added).
- **Naming:** `<ComponentName>.test.ts` co-located with component.
- **E2E (later):** Playwright for critical user flows.

### 5.3 Test Data

See [test-data.md](../testing/test-data.md) for seed specifications:

- ~40 students across cohorts sharing a GE course
- Professors including one effective-dated handover
- 6 weeks of historical attendance

> **Note:** Programs and year levels are admin-created, not seeded.

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
PUBLIC_API_URL=http://localhost:8000   # required
```

---

## 7. Documentation Standards

- All new docs go in the appropriate `docs/` subdirectory.
- Cross-reference other docs with relative links: `[API Contracts](../architecture/api-contracts.md)`.
- Reference Decision Log IDs when citing decisions: `(D12)`.
- Wireframes use ASCII boxes, 700x520 canvas, conventions from §9 of the Refactor Plan.
- Screenshots in user guides use `[FIG: description]` placeholders.
- Every glossary term links to `docs/project/glossary.md`.
