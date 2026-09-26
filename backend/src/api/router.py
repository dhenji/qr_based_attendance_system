from fastapi import APIRouter

from features.admin.router import router as admin_router
from features.attendance.router import router as attendance_router
from features.auth.router import router as auth_router
from features.professor.router import router as professor_router
from features.session.router import router as session_router
from features.student.router import router as student_router

api_router = APIRouter(prefix="/api")

# Each feature router bakes its own contract path into its prefix, so nothing is
# passed here. One APIRouter per mount point - a feature folder that spans two
# prefixes (e.g. course -> /admin/courses and /admin/offerings) declares a
# second APIRouter in its own module.
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(student_router, tags=["student"])
api_router.include_router(session_router, tags=["session"])
api_router.include_router(attendance_router, tags=["attendance"])
api_router.include_router(professor_router, tags=["professor"])
api_router.include_router(admin_router, tags=["admin"])
