from fastapi import APIRouter

# This module owns /admin/courses ONLY.
#
# The course feature spans TWO mount points, so it needs TWO routers:
#   course/router.py          -> /admin/courses   (Course template CRUD)
#   course/offering_router.py -> /admin/offerings (CourseOffering CRUD)
# Do not add offering routes here — they would register as
# /api/admin/courses/{id}/... instead of /api/admin/offerings/{id}/...
#
# Prefix baked in here; mounted with no prefix= argument in api/router.py.
# Collection routes use "" not "/" so the registered path matches the contract
# exactly.
router = APIRouter(prefix="/admin/courses")
