from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_request_settings, require_auth
from app.config import Settings
from app.db import get_session
from app.models import AppSetting, CatalogColor, CatalogPart, CatalogSet, SyncRun
from app.services.backup import BACKUP_SCHEMA

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_auth)])


@router.get("/status")
def status(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    settings: Settings = get_request_settings(request)
    configured = bool(settings.rebrickable_api_key) or session.scalar(select(AppSetting).where(AppSetting.key == "rebrickable_api_key", AppSetting.secret.is_(True))) is not None
    completed = session.scalar(select(SyncRun).where(SyncRun.status == "completed").order_by(SyncRun.completed_at.desc(), SyncRun.id.desc()))
    failed = session.scalar(select(SyncRun).where(SyncRun.status == "failed").order_by(SyncRun.completed_at.desc(), SyncRun.id.desc()))
    return {
        "api_key_configured": configured,
        "last_successful_import": None if completed is None else completed.completed_at,
        "latest_failed_import": None if failed is None else failed.completed_at,
        "catalog_counts": {
            "sets": session.scalar(select(func.count()).select_from(CatalogSet)) or 0,
            "parts": session.scalar(select(func.count()).select_from(CatalogPart)) or 0,
            "colors": session.scalar(select(func.count()).select_from(CatalogColor)) or 0,
        },
        "database_label": settings.database_url.rsplit("/", 1)[-1],
        "backup_schema": BACKUP_SCHEMA,
    }
