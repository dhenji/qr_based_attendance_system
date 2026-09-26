from fastapi import APIRouter

# Prefix baked in here; mounted without a prefix argument in api/router.py.
router = APIRouter(prefix="/student")
