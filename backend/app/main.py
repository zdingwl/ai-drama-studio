from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import install_exception_handlers
from app.core.time import utc_now
from app.db.session import SessionLocal
from app.replica_pipeline.asset_images import reconcile_interrupted_asset_workspace_tasks
from app.workflow.dispatcher import PersistentTaskDispatcher
from app.workflow.task_service import mark_interrupted_tasks


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.ensure_runtime_directories()
    # A process restart means no in-process worker from the previous process can still own a
    # RUNNING task. Reconcile those rows before the persistent dispatcher starts consuming QUEUED
    # work so the UI never keeps a false "generating" state after a backend restart.
    with SessionLocal() as db:
        interrupted = mark_interrupted_tasks(db, stale_before=utc_now())
        reconcile_interrupted_asset_workspace_tasks(db, interrupted)
    dispatcher = PersistentTaskDispatcher(SessionLocal)
    dispatcher.start()
    try:
        yield
    finally:
        dispatcher.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="3.0.0",
        lifespan=lifespan,
    )
    install_exception_handlers(application)
    application.include_router(api_router, prefix=settings.api_prefix)
    return application


app = create_app()
