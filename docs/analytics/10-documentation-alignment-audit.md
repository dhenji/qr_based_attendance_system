# 10 — Documentation Alignment Audit

## Discrepancy table

| Doc + section | Documented | Actual | Evidence | Why | Fix |
|---|---|---|---|---|---|
| `risk-model.md §2.2` | Absence numerator excludes `late`/`excused`; rejected dropped | `_usable_records` drops rejected; `_status_count(..., ABSENT)` | `analytics/batch.py:91-95,159` | Verified | OK |
| `risk-model.md §2.3` | Pending does not break streak | `_longest_absence_streak`: pending `continue` | `analytics/batch.py:107-120` | Verified | OK |
| `api-contracts.md` analytics | course-options derived from offerings | `_offerings_stmt` predicate; no catalogue listing | `analytics/service.py:375-400` | ADR-085 | Verified |
| `data-flow.md` analytics scope | (none) | `course_ids` honored by overview/comparison/trends/at-risk/staging + promote | `analytics/router.py`, `analytics/service.py` | ADR-085 | Cross-ref |
| `project-structure.md` | router counts | Analytics one router at `/admin/analytics` | `analytics/router.py:30` | Verified | OK |

## Known gaps / not implemented

- Risk probability is a synthetic sort/display score, not a true ML probability
  (`risk-model.md §3.1`).
- Dry-run (`RISK_BATCH_DRY_RUN`) writes staging; promotion is manual.
- Cohort comparison paginates after grouping, so `total` is cohort count, not
  offering count.
- Course options has no `is_active` gate, so archived offerings with history
  stay reachable.
- Frontend analytics page error handling relies on `client.ts` normalization.
