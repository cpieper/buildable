from datetime import UTC, datetime

from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy.orm import Session, sessionmaker

from app.models import AppSetting, CatalogColor, CatalogPart, CatalogSet, SyncRun


def test_backup_and_status_routes_require_authentication(client: TestClient) -> None:
    assert client.get("/api/backups/export").status_code == 401
    assert client.post("/api/backups/validate", json={}).status_code == 401
    assert client.get("/api/settings/status").status_code == 401


def test_backup_routes_export_validate_import_and_write_safety_copy(
    client: TestClient, session_factory: sessionmaker[Session], app: object
) -> None:
    with session_factory.begin() as session:
        session.add_all([
            AppSetting(key="auth.password_hash", value=PasswordHash.recommended().hash("build-stuff"), secret=True),
            AppSetting(key="auth.revision", value="1", secret=True),
            CatalogSet(set_num="1000-1", name="One", num_parts=0, source="test"),
            CatalogPart(part_num="3001", name="Brick", external_ids_json="{}"),
            CatalogColor(id=5, name="Red", rgb_hex="C91A09", external_ids_json="{}"),
        ])
    assert client.post("/api/auth/login", json={"password": "build-stuff"}).status_code == 204
    exported = client.get("/api/backups/export")
    assert exported.status_code == 200
    payload = exported.json()
    payload["owned_sets"] = [{"set_num": "1000-1", "quantity": 1, "completeness": "complete", "unknown_missing_count": 0, "unknown_missing_note": None, "notes": None}]
    assert client.post("/api/backups/validate", json=payload).json() == {"valid": True, "missing_dependencies": {}}
    assert client.post("/api/backups/import", params={"mode": "replace"}, json=payload).status_code == 422
    restored = client.post("/api/backups/import", params={"mode": "replace", "confirm": "true"}, json=payload)
    assert restored.status_code == 200
    safety_name = restored.json()["safety_backup"]
    assert safety_name is not None
    assert (app.state.settings.data_dir / "backups" / safety_name).exists()  # type: ignore[attr-defined]


def test_status_reports_operational_metadata(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory.begin() as session:
        session.add_all([
            AppSetting(key="auth.password_hash", value=PasswordHash.recommended().hash("build-stuff"), secret=True),
            AppSetting(key="auth.revision", value="1", secret=True),
            AppSetting(key="rebrickable_api_key", value="secret", secret=True),
            CatalogSet(set_num="1000-1", name="One", num_parts=0, source="test"),
            SyncRun(source="catalog", status="completed", started_at=datetime.now(UTC), completed_at=datetime.now(UTC)),
            SyncRun(source="catalog", status="failed", started_at=datetime.now(UTC), completed_at=datetime.now(UTC), error="bad"),
        ])
    client.post("/api/auth/login", json={"password": "build-stuff"})
    body = client.get("/api/settings/status").json()
    assert body["api_key_configured"] is True
    assert body["catalog_counts"]["sets"] == 1
    assert body["last_successful_import"] is not None
    assert body["latest_failed_import"] is not None
    assert body["backup_schema"] == "what2build.backup/v1"


def test_replace_aborts_when_safety_backup_cannot_be_written(
    client: TestClient, session_factory: sessionmaker[Session], monkeypatch: object
) -> None:
    import app.api.backups as backups_api

    with session_factory.begin() as session:
        session.add_all([
            AppSetting(key="auth.password_hash", value=PasswordHash.recommended().hash("build-stuff"), secret=True),
            AppSetting(key="auth.revision", value="1", secret=True),
            CatalogSet(set_num="1000-1", name="One", num_parts=0, source="test"),
        ])
    client.post("/api/auth/login", json={"password": "build-stuff"})

    def fail_write(*_args: object) -> None:
        raise OSError("read only")

    monkeypatch.setattr(backups_api, "write_backup_json", fail_write)  # type: ignore[attr-defined]
    payload = {"schema": "what2build.backup/v1", "exported_at": "2026-08-10T12:00:00Z", "owned_sets": [{"set_num": "1000-1", "quantity": 1, "completeness": "complete", "unknown_missing_count": 0, "unknown_missing_note": None, "notes": None}], "missing_parts": [], "set_overrides": [], "set_part_overrides": [], "equivalence_groups": [], "settings": {}}
    assert client.post("/api/backups/import?mode=replace&confirm=true", json=payload).status_code == 500


def test_replace_rejects_reserved_setting_before_writing_safety_copy(
    client: TestClient, session_factory: sessionmaker[Session], monkeypatch: object
) -> None:
    import app.api.backups as backups_api

    with session_factory.begin() as session:
        session.add_all([
            AppSetting(key="auth.password_hash", value=PasswordHash.recommended().hash("build-stuff"), secret=True),
            AppSetting(key="auth.revision", value="1", secret=True),
        ])
    client.post("/api/auth/login", json={"password": "build-stuff"})

    def unexpected_write(*_args: object) -> None:
        raise AssertionError("safety backup should not be written")

    monkeypatch.setattr(backups_api, "write_backup_json", unexpected_write)  # type: ignore[attr-defined]
    payload = {"schema": "what2build.backup/v1", "exported_at": "2026-08-10T12:00:00Z", "owned_sets": [], "missing_parts": [], "set_overrides": [], "set_part_overrides": [], "equivalence_groups": [], "settings": {"auth.password_hash": "malicious"}}
    response = client.post("/api/backups/import?mode=replace&confirm=true", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "reserved_setting_key"
