from fastapi import APIRouter

from app.api.routes.evidence import router as evidence_router
from app.api.routes.health import router as health_router
from app.api.routes.preprocessing import router as preprocessing_router
from app.api.routes.projects import router as projects_router
from app.api.routes.shot_breakdown import router as shot_breakdown_router
from app.api.routes.skills import router as skills_router
from app.api.routes.source_analysis import router as source_analysis_router
from app.api.routes.source_resolution import router as source_resolution_router
from app.api.routes.source_snapshot import router as source_snapshot_router
from app.api.routes.sources import router as sources_router
from app.api.routes.target_assets import router as target_assets_router
from app.api.routes.target_bible import router as target_bible_router
from app.api.routes.target_script import router as target_script_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.understanding import router as understanding_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(projects_router)
api_router.include_router(skills_router)
api_router.include_router(sources_router)
api_router.include_router(preprocessing_router)
api_router.include_router(evidence_router)
api_router.include_router(understanding_router)
api_router.include_router(shot_breakdown_router)
api_router.include_router(source_resolution_router)
api_router.include_router(source_snapshot_router)
api_router.include_router(source_analysis_router)
api_router.include_router(target_bible_router)
api_router.include_router(target_script_router)
api_router.include_router(target_assets_router)
api_router.include_router(tasks_router)
