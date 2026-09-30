from __future__ import annotations

from fastapi import APIRouter

# INTENTIONALLY UNMOUNTED.
#
# The contract defines NO enrollment mount point. Both enrollment endpoints are
# nested under the offerings router:
#   POST /admin/offerings/{oid}/enrollments/bulk   -> course/offering_router.py
#   GET  /admin/offerings/{oid}/students           -> course/offering_router.py
#
# Enrollment logic (bulk_enroll, roster read) lives in the offering service.
# Do NOT add `include_router(enrollment_router)` to api/router.py — that would
# create an undocumented /api/enrollments surface.
#
# This stub is kept so the file inventory matches the 14-slice layout, and is
# listed as unmounted alongside features/course.
router = APIRouter()
