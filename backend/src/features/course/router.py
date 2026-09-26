from fastapi import APIRouter

# Phase 3 (ADR-057). This module owns /admin/courses ONLY.
#
# The course feature spans TWO mount points, so it needs TWO routers:
#   course/router.py         -> /admin/courses    (Course template CRUD, PROMPT 3.3)
#   course/offering_router.py -> /admin/offerings (CourseOffering CRUD, PROMPT 3.3b)
# Do not add offering routes here — they would register as
# /api/admin/courses/{id}/... instead of /api/admin/offerings/{id}/...
#
# Prefix baked in per feature-template.md section 5; mounted with no prefix=
# argument in api/router.py. Collection routes use "" not "/" so the registered
# path matches the contract exactly.
router = APIRouter(prefix="/admin/courses")
