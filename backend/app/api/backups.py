from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_request_settings, require_auth
from app.config import Settings
from app.db import get_session
from app.schemas.backup import BackupV1, BackupValidationResponse, RestoreSummary
from app.services.backup import (
    BackupValidationError,
    export_backup,
    restore_backup,
    validate_backup,
    write_backup_json,
)

router = APIRouter(prefix="/api/backups", tags=["backups"], dependencies=[Depends(require_auth)])


def _validation_error(error: BackupValidationError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": error.code, "message": str(error), "missing_dependencies": error.dependencies})


@router.get("/export", response_model=BackupV1, response_model_by_alias=True)
def export(session: Annotated[Session, Depends(get_session)]) -> BackupV1:
    return export_backup(session)


@router.post("/validate", response_model=BackupValidationResponse)
def validate(payload: BackupV1, session: Annotated[Session, Depends(get_session)]) -> BackupValidationResponse:
    try:
        validate_backup(session, payload)
    except BackupValidationError as error:
        raise _validation_error(error) from error
    return BackupValidationResponse(valid=True)


@router.post("/import", response_model=RestoreSummary)
def import_backup(
    payload: BackupV1,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    mode: Annotated[str, Query(pattern="^(replace|merge)$")] = "merge",
    confirm: bool = False,
) -> RestoreSummary:
    if mode == "replace" and not confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="replace restore requires confirm=true")
    try:
        validate_backup(session, payload)
    except BackupValidationError as error:
        raise _validation_error(error) from error
    safety_backup = None
    if mode == "replace":
        settings: Settings = get_request_settings(request)
        safety_backup = f"before-restore-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}.json"
        try:
            write_backup_json(settings.data_dir / "backups" / safety_backup, export_backup(session))
        except OSError as error:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to write safety backup; restore was not started") from error
    try:
        summary = restore_backup(session, payload, mode)
    except BackupValidationError as error:
        raise _validation_error(error) from error
    summary.safety_backup = safety_backup
    return summary
