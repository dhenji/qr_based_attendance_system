from fastapi import APIRouter

# ALREADY MOUNTED at /api/professor (see api/router.py). Professor-facing
# routes only. NOTE: `features/session/router.py` shares this same /professor
# mount point — several routers may share a prefix, but their inner paths must
# not collide (session owns /professor/sessions/*).
#
# DO NOT change this prefix and DO NOT mount this router a second time.
# Admin professor CRUD (PROMPT 3.5/3.9, /admin/professors) belongs to a
# SEPARATE module, `professor/admin_router.py` with
# `APIRouter(prefix="/admin/professors")` — see ADR-057. Mounting THIS router
# under /api/admin would also expose /api/admin/courses and
# /api/admin/sessions, which the contract does not define there.
router = APIRouter(prefix="/professor")
