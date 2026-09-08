from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.api.routes.projects import router as projects_router
from app.api.routes.skills import router as skills_router
from app.api.routes.sources import router as sources_router
from app.api.routes.tasks import router as tasks_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(projects_router)
api_router.include_router(skills_router)
api_router.include_router(sources_router)
api_router.include_router(tasks_router)
