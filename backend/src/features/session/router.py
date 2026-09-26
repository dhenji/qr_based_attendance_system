from fastapi import APIRouter

# Session routes are professor-scoped. Prefix baked in per feature-template.md section 5.
router = APIRouter(prefix="/professor")
