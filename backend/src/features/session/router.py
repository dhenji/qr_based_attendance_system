from fastapi import APIRouter

# Session routes are professor-scoped; the prefix is baked in here and the
# router is mounted without a prefix argument in api/router.py.
router = APIRouter(prefix="/professor")
