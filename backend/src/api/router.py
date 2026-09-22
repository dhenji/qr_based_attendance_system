from fastapi import APIRouter

from features.admin.router import router as admin_router
from features.attendance.router import router as attendance_router
from features.auth.router import router as auth_router
from features.professor.router import router as professor_router
from features.session.router import router as session_router
from features.student.router import router as student_router

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(student_router, prefix="/student", tags=["student"])
api_router.include_router(session_router, prefix="/professor", tags=["session"])
api_router.include_router(attendance_router, prefix="/student", tags=["attendance"])
api_router.include_router(professor_router, prefix="/professor", tags=["professor"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
