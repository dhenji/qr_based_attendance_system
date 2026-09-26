from fastapi import APIRouter

# Prefix baked in per feature-template.md section 5; mounted without a prefix in api/router.py.
router = APIRouter(prefix="/student")
