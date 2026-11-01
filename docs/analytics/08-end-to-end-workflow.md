# 08 — End-to-End Workflow

## Overview / comparison / trends

```mermaid
sequenceDiagram
    participant A as Admin Client
    participant API as Server API
    participant DB as Database
    A->>API: GET /admin/analytics/overview?program_id&year_level_id&semester&course_ids&session_type&date_from&date_to
    API->>DB: offerings via _offerings_stmt → sessions → enrollments → attendance tallies
    API->>API: attendance_rates(present, late, excused, enrolled)
    API-->>A: 200 {total_students, total_courses, avg_compliance_rate, avg_participation_rate, total_sessions, lecture_sessions, lab_sessions}
```

## At-risk

Reads stored risk rows; feature values from JSONB snapshot. Ordered by
`risk_probability` desc.

## Risk refresh

`POST /admin/analytics/refresh-risk` resolves enrollment targets (full batch if
no filters) and recomputes + upserts synchronously; rate-limited 1/60s.

## Staging / promote

Dry-run writes staging rows; promote copies scoped rows into live scores.

## Course options

`GET /admin/analytics/course-options` returns courses with at least one
in-scope offering, supporting search and limit.
```
