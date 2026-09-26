from fastapi import APIRouter

# ALREADY MOUNTED at /api/student (see api/router.py). Student-facing routes
# only: profile, schedule, attendance scan/history, excuse requests, face status.
#
# DO NOT change this prefix and DO NOT mount this router a second time.
# Admin student CRUD (PROMPT 3.4/3.9, /admin/students) belongs to a SEPARATE
# module, `student/admin_router.py` with `APIRouter(prefix="/admin/students")`
# — see ADR-057. Routes inside a router are relative to its own prefix, so
# mounting THIS router under /api/admin would also expose /api/admin/profile,
# /api/admin/schedule and /api/admin/attendance, none of which the contract
# defines. One APIRouter per (feature, mount point).
router = APIRouter(prefix="/student")
