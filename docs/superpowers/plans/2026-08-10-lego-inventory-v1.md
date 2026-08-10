# LEGO Inventory V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first web application that turns owned official LEGO sets into a combined piece inventory and explains which cached official sets are exact-buildable, substitution-buildable, or still missing pieces.

**Architecture:** FastAPI owns a synchronous SQLAlchemy 2.0 domain and persistence layer backed by SQLite. SvelteKit builds a client-rendered static application that talks to `/api`; in production FastAPI serves both the API and the compiled frontend from one container/process. Catalog imports remain immutable, local corrections are layered at read time, and the pure matcher consumes an explicit inventory snapshot.

**Tech Stack:** Python 3.11+, uv, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, SQLite, HTTPX, pytest; Node.js 22+, npm, SvelteKit/Svelte 5, TypeScript, adapter-static, lucide-svelte, Vitest, Testing Library, Playwright; Docker Compose for Raspberry Pi deployment.

## Global Constraints

- V1 supports official LEGO sets only; MOCs and alternate builds remain future work.
- Color is a soft constraint: a same-part different-color match counts as buildable and must be highlighted.
- Non-color substitutions are allowed only through explicit local equivalence groups.
- Target requirements exclude spare rows; intact owned sets may contribute spare rows to available inventory.
- Known missing pieces reduce inventory; unknown missing counts and notes only create confidence warnings.
- V1 evaluates one target against a full inventory snapshot and never reserves pieces.
- Imported catalog records are immutable; local metadata and inventory corrections are stored separately and applied visibly.
- Rebrickable API access is optional, targeted, and throttling-aware; ZIP/CSV and manual entry work without an API key.
- Authentication is one shared password with no accounts or roles.
- JSON backups exclude the password hash, session secret, and Rebrickable API key.
- Production targets 64-bit Raspberry Pi OS or Debian 12+ and stores mutable data beneath `/data`.
- UI uses the approved Workshop Rail shell, Builder's Bench match detail, and Inventory Ledger table; it must work at 390px and 1280px widths.
- Scanner entry, build planning, loose pieces, storage locations, build history, scheduled sync, and stored instruction PDFs are documented future features, not partial V1 controls.

---

## File Map

Backend responsibilities:

- `backend/pyproject.toml`: Python package metadata, runtime dependencies, and pytest/ruff configuration.
- `backend/app/config.py`: environment-backed settings and filesystem paths.
- `backend/app/db.py`: engine/session construction and SQLite pragmas.
- `backend/app/models.py`: imported catalog, collection, override, equivalence, sync, and setting ORM models.
- `backend/app/schemas/`: Pydantic request/response contracts grouped by feature.
- `backend/app/repositories/catalog.py`: effective catalog reads with local overrides applied.
- `backend/app/services/inventory.py`: combined available-inventory computation.
- `backend/app/services/matcher.py`: pure, database-free buildability algorithm.
- `backend/app/services/catalog_import.py`: transactional manual and Rebrickable ZIP imports.
- `backend/app/services/rebrickable.py`: targeted remote lookup client and response mapping.
- `backend/app/services/backup.py`: versioned backup export, validation, and restore.
- `backend/app/api/`: thin FastAPI routers for auth, catalog, collection, inventory, matches, recommendations, settings, and backups.
- `backend/tests/`: unit and API tests with isolated temporary SQLite databases.

Frontend responsibilities:

- `frontend/src/lib/api/`: typed fetch wrapper and API DTOs.
- `frontend/src/lib/components/shell/`: Workshop Rail navigation, mobile bar, status marks, and shared page chrome.
- `frontend/src/lib/components/collection/`: owned-set list, add/edit dialog, and missing-piece editor.
- `frontend/src/lib/components/inventory/`: Inventory Ledger rows, color expansion, warning summary, and filters.
- `frontend/src/lib/components/matches/`: recommendation row, match meter, substitution story, and missing-parts table.
- `frontend/src/routes/`: unlock, collection, inventory, buildable sets, target detail, and settings screens.
- `frontend/e2e/`: full user-flow Playwright coverage.

Operations responsibilities:

- `Dockerfile`: multi-stage Svelte build plus Python runtime image, compatible with ARM64.
- `compose.yaml`: one app service, `/data` volume, environment, health check, and LAN port.
- `scripts/reset-password.sh`: documented local password-reset path.
- `.env.example`: non-secret configuration contract.
- `README.md`: macOS development, catalog setup, backup, and Raspberry Pi deployment.

---

### Task 1: Runnable Project Foundation

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/test_health.py`
- Create: `frontend/package.json` and SvelteKit scaffold files
- Create: `frontend/src/routes/+layout.ts`
- Create: `frontend/src/routes/+page.svelte`
- Create: `frontend/src/app.css`
- Create: `Makefile`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: no application code.
- Produces: `app.main:create_app() -> FastAPI`, `GET /api/health -> {"status":"ok"}`, frontend scripts `check`, `test`, `build`, and root commands `make dev`, `make test`, `make check`.

- [ ] **Step 1: Scaffold the backend and frontend dependency manifests**

Run:

```bash
mkdir -p backend/app backend/tests
cd backend
uv init --lib --name what2build-api --python '>=3.11'
uv add 'fastapi[standard]' 'pydantic-settings>=2,<3' 'sqlalchemy>=2,<3' 'alembic>=1.16,<2' 'httpx>=0.28,<1' 'pwdlib[argon2]>=0.3,<1' 'itsdangerous>=2.2,<3' 'python-multipart>=0.0.20,<1'
uv add --dev 'pytest>=8,<10' 'pytest-cov>=6,<8' 'ruff>=0.12,<1'
cd ..
npx sv create frontend --template minimal --types ts --no-add-ons --install npm
cd frontend
npm install lucide-svelte
npm install --save-dev @sveltejs/adapter-static vitest @testing-library/svelte @testing-library/jest-dom jsdom @playwright/test
```

Remove scaffold demo content, set SvelteKit to `adapter-static`, set `ssr = false` and `prerender = true` in `+layout.ts`, and add npm scripts:

```json
{
  "scripts": {
    "dev": "vite --host 0.0.0.0",
    "build": "vite build",
    "check": "svelte-kit sync && svelte-check --tsconfig ./tsconfig.json",
    "test": "vitest run",
    "test:e2e": "playwright test"
  }
}
```

Configure Vite's development server to proxy `/api` to `http://127.0.0.1:8000`; production keeps the same relative URLs because FastAPI serves both surfaces.

- [ ] **Step 2: Write the failing health test**

```python
# backend/tests/test_health.py
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_check() -> None:
    response = TestClient(create_app()).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_health.py -v`

Expected: FAIL because `app.main` or `create_app` does not exist.

- [ ] **Step 4: Implement the minimal app factory and configuration**

```python
# backend/app/config.py
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/what2build.db"
    data_dir: Path = Path("./data")
    frontend_dir: Path | None = None
    session_secret: str = "development-only-change-me"
    secure_cookies: bool = False
    rebrickable_api_key: str | None = None

    model_config = SettingsConfigDict(env_prefix="WHAT2BUILD_", env_file=".env")


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```python
# backend/app/main.py
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="What2Build", version="0.1.0")

    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 5: Add the root developer commands and ignore generated state**

The `Makefile` must run backend and frontend checks separately and start both dev servers:

```makefile
.PHONY: dev test check

dev:
	trap 'kill 0' EXIT; (cd backend && uv run fastapi dev app/main.py --host 0.0.0.0 --port 8000) & (cd frontend && npm run dev -- --port 5173) & wait

test:
	cd backend && uv run pytest
	cd frontend && npm test

check:
	cd backend && uv run ruff check app tests
	cd frontend && npm run check
	cd frontend && npm run build
```

Add `backend/data/`, `.env`, `.venv/`, `node_modules/`, `frontend/build/`, `frontend/test-results/`, and `frontend/playwright-report/` to `.gitignore`.

- [ ] **Step 6: Run foundation verification**

Run:

```bash
cd backend && uv run pytest tests/test_health.py -v
cd ../frontend && npm run check && npm run build
```

Expected: health test passes; Svelte check and static build exit 0.

- [ ] **Step 7: Commit**

```bash
git add .gitignore Makefile backend frontend
git commit -m "chore: scaffold FastAPI and SvelteKit application"
```

---

### Task 2: SQLite Schema And Effective Catalog Repository

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/migrations/env.py`
- Create: `backend/migrations/versions/0001_initial_schema.py`
- Create: `backend/app/db.py`
- Create: `backend/app/models.py`
- Create: `backend/app/repositories/catalog.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/repositories/test_catalog.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `Settings.database_url`, `create_app()`.
- Produces: `get_session() -> Iterator[Session]`, ORM tables, `CatalogRepository.search_sets(query, limit)`, `CatalogRepository.get_effective_set(set_num) -> EffectiveSet | None`, and `EffectivePartRow(part_num, color_id, quantity, is_spare, source_kind)`.

- [ ] **Step 1: Write repository tests for immutable imports plus local overlays**

```python
def test_effective_set_applies_metadata_and_inventory_overrides(session):
    seed_catalog_set(session, set_num="1234-1", name="Original")
    seed_catalog_part_row(session, "1234-1", "3001", 5, quantity=2)
    session.add(CatalogSetOverride(set_num="1234-1", name="Corrected"))
    session.add(CatalogSetPartOverride(
        set_num="1234-1", part_num="3001", color_id=5,
        operation="upsert", quantity=3, is_spare=False,
    ))
    session.commit()

    result = CatalogRepository(session).get_effective_set("1234-1")

    assert result is not None
    assert result.name == "Corrected"
    assert [(row.part_num, row.color_id, row.quantity) for row in result.parts] == [
        ("3001", 5, 3)
    ]


def test_delete_override_hides_imported_inventory_row(session):
    seed_catalog_set(session, set_num="1234-1", name="Original")
    seed_catalog_part_row(session, "1234-1", "3001", 5, quantity=2)
    session.add(CatalogSetPartOverride(
        set_num="1234-1", part_num="3001", color_id=5,
        operation="delete", quantity=None, is_spare=False,
    ))
    session.commit()

    assert CatalogRepository(session).get_effective_set("1234-1").parts == []
```

- [ ] **Step 2: Run the repository tests to verify they fail**

Run: `cd backend && uv run pytest tests/repositories/test_catalog.py -v`

Expected: FAIL because the models and repository do not exist.

- [ ] **Step 3: Define the normalized schema and first migration**

Create typed SQLAlchemy 2.0 models for:

```text
catalog_sets(set_num PK, name, year, theme_id, theme_name, num_parts, image_url,
             external_url, instructions_url, source, source_updated_at, imported_at)
catalog_parts(part_num PK, name, category_name, image_url, external_ids_json)
catalog_colors(id PK, name, rgb_hex, external_ids_json)
catalog_set_parts(id PK, set_num FK, part_num FK, color_id FK, quantity,
                  is_spare, source_kind, source_id,
                  UNIQUE set/part/color/spare/source_kind/source_id)
owned_sets(id PK, set_num FK, quantity, completeness, unknown_missing_count,
           unknown_missing_note, notes, added_at, updated_at)
owned_set_missing_parts(id PK, owned_set_id FK, part_num FK, color_id FK,
                        quantity, note)
catalog_set_overrides(set_num PK/FK, name, year, theme_name, num_parts,
                      image_url, external_url, instructions_url, reason, updated_at)
catalog_set_part_overrides(id PK, set_num FK, part_num FK, color_id FK,
                           is_spare, operation, quantity, reason, updated_at,
                           UNIQUE set/part/color/is_spare)
equivalence_groups(id PK, name UNIQUE, notes, created_at, updated_at)
equivalence_members(group_id FK, part_num FK, PRIMARY KEY group/part)
app_settings(key PK, value, secret, updated_at)
sync_runs(id PK, source, status, started_at, completed_at, summary_json, error)
```

Use checks for positive quantities, `completeness IN ('complete','incomplete')`, and override `operation IN ('upsert','delete')`. Enable `PRAGMA foreign_keys=ON`, `journal_mode=WAL`, and a 5-second busy timeout in `db.py`.

- [ ] **Step 4: Implement effective catalog reads**

Define immutable result dataclasses:

```python
@dataclass(frozen=True)
class EffectivePartRow:
    part_num: str
    part_name: str
    color_id: int
    color_name: str
    rgb_hex: str
    quantity: int
    is_spare: bool
    source_kind: str
    image_url: str | None


@dataclass(frozen=True)
class EffectiveSet:
    set_num: str
    name: str
    year: int | None
    theme_name: str | None
    num_parts: int
    image_url: str | None
    external_url: str | None
    instructions_url: str | None
    has_local_overrides: bool
    parts: list[EffectivePartRow]
```

`get_effective_set()` must load imported rows, replace nullable metadata fields with non-null override values, aggregate source rows, and apply delete/upsert inventory overrides keyed by `(part_num, color_id, is_spare)`. A spare classification change is represented by deleting the old identity and upserting the new identity. Return rows sorted by part name and color name. Never update an imported table.

- [ ] **Step 5: Add isolated database fixtures and app lifespan migration**

`tests/conftest.py` must create a temporary SQLite file per test, run `Base.metadata.create_all`, and override `get_session`. App startup creates `Settings.data_dir` and runs Alembic `upgrade head`; tests may disable startup migration through an injected session factory.

- [ ] **Step 6: Run schema and repository verification**

Run:

```bash
cd backend
uv run alembic upgrade head
uv run pytest tests/repositories/test_catalog.py -v
uv run ruff check app tests
```

Expected: migration succeeds on an empty database and all repository tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/alembic.ini backend/migrations backend/app backend/tests
git commit -m "feat: add catalog and collection persistence model"
```

---

### Task 3: Shared-Password Authentication

**Files:**
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/services/auth.py`
- Create: `backend/app/api/dependencies.py`
- Create: `backend/app/api/auth.py`
- Create: `backend/app/cli.py`
- Create: `backend/tests/api/test_auth.py`
- Modify: `backend/app/main.py`
- Modify: `backend/pyproject.toml`

**Interfaces:**
- Consumes: `AppSetting`, `get_session()`, `Settings.session_secret`, `Settings.secure_cookies`.
- Produces: `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/session`, `POST /api/auth/password`; `require_auth(request, session) -> None`; CLI `what2build reset-password`.

- [ ] **Step 1: Write failing API tests for login, session protection, logout, and revision invalidation**

```python
def test_login_sets_http_only_session_cookie(client, password_store):
    password_store.set_password("build-stuff")

    response = client.post("/api/auth/login", json={"password": "build-stuff"})

    assert response.status_code == 204
    assert "what2build_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert client.get("/api/auth/session").json() == {"authenticated": True}


def test_password_change_invalidates_existing_session(client, password_store):
    password_store.set_password("old-password")
    client.post("/api/auth/login", json={"password": "old-password"})
    old_cookie = client.cookies.get("what2build_session")

    response = client.post("/api/auth/password", json={
        "current_password": "old-password", "new_password": "new-password"
    })

    assert response.status_code == 204
    client.cookies.set("what2build_session", old_cookie)
    assert client.get("/api/auth/session").status_code == 401
```

- [ ] **Step 2: Verify the auth tests fail**

Run: `cd backend && uv run pytest tests/api/test_auth.py -v`

Expected: FAIL with missing auth routes.

- [ ] **Step 3: Implement password hashing and signed revisioned sessions**

Store `auth.password_hash` and integer `auth.revision` in `app_settings` with `secret=True`. Use `pwdlib.PasswordHash.recommended()` for verify/hash. Sign a payload `{"authenticated": true, "revision": N}` using `itsdangerous.URLSafeTimedSerializer`, reject cookies older than 30 days, and compare the embedded revision to the database value on every protected request.

Cookie requirements:

```python
response.set_cookie(
    "what2build_session",
    token,
    httponly=True,
    secure=settings.secure_cookies,
    samesite="lax",
    max_age=60 * 60 * 24 * 30,
    path="/",
)
```

Password change and CLI reset must increment `auth.revision`. Login errors always return `401 {"detail":"Invalid password"}`.

Register `[project.scripts] what2build = "app.cli:main"` in `pyproject.toml`; the CLI opens the configured database through the same settings/session factory as the web app.

- [ ] **Step 4: Register the auth router and protect a probe route in tests**

Use `APIRouter(prefix="/api/auth")`. `GET /api/auth/session` is the only session-status probe; all later feature routers include `dependencies=[Depends(require_auth)]`.

- [ ] **Step 5: Run auth and regression tests**

Run: `cd backend && uv run pytest tests/api/test_auth.py tests/test_health.py -v`

Expected: all tests pass; health remains public.

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests backend/pyproject.toml backend/uv.lock
git commit -m "feat: protect the app with a shared password"
```

---

### Task 4: Transactional Catalog Imports

**Files:**
- Create: `backend/app/schemas/catalog.py`
- Create: `backend/app/services/catalog_import.py`
- Create: `backend/app/api/catalog.py`
- Create: `backend/tests/fixtures/rebrickable-small/` CSV fixtures
- Create: `backend/tests/services/test_catalog_import.py`
- Create: `backend/tests/api/test_catalog.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: catalog ORM models, `CatalogRepository`, `require_auth`.
- Produces: `import_rebrickable_zip(stream, session) -> ImportSummary`, `import_manual_set(payload, session) -> EffectiveSet`, `POST /api/catalog/import`, `POST /api/catalog/manual-sets`, `GET /api/catalog/sets`, `GET /api/catalog/sets/{set_num}`.

- [ ] **Step 1: Write failing tests for CSV identity, minifig expansion, spares, duplicate rows, and rollback**

```python
def test_zip_import_preserves_color_and_expands_minifig_parts(session, zip_fixture):
    summary = import_rebrickable_zip(zip_fixture("valid-catalog.zip"), session)
    result = CatalogRepository(session).get_effective_set("1234-1")

    assert summary.sets == 1
    assert ("3001", 5, 2, False, "set") in part_tuples(result.parts)
    assert ("3626", 14, 1, False, "minifig") in part_tuples(result.parts)
    assert ("6141", 1, 1, True, "set") in part_tuples(result.parts)


def test_malformed_zip_rolls_back_every_catalog_change(session, zip_fixture):
    with pytest.raises(CatalogImportError, match="inventory_parts.csv:2"):
        import_rebrickable_zip(zip_fixture("bad-quantity.zip"), session)

    assert session.scalar(select(func.count()).select_from(CatalogSet)) == 0
```

- [ ] **Step 2: Verify import tests fail**

Run: `cd backend && uv run pytest tests/services/test_catalog_import.py -v`

Expected: FAIL because the importer is undefined.

- [ ] **Step 3: Implement validated ZIP/CSV import**

Accept one ZIP containing `sets.csv`, `themes.csv`, `parts.csv`, `part_categories.csv`, `colors.csv`, `inventories.csv`, `inventory_parts.csv`, `inventory_minifigs.csv`, and `minifigs.csv`. Stream each member through `csv.DictReader`; reject missing files, duplicate primary identities, unknown references, non-integer IDs, and non-positive non-spare quantities with filename and row number.

Choose the highest inventory version for each set. Import its direct part rows, then expand each `inventory_minifigs` row through the matching minifig inventory and multiply quantities. Keep source rows separate through `source_kind` and aggregate only identical `(set, part, color, spare, source_kind, source_id)` identities. Perform staging, validation, and replacement in one transaction. On failure, roll that transaction back and record the failed `SyncRun` in a fresh transaction so no partial catalog rows survive; on success, record the completed run with the catalog commit.

- [ ] **Step 4: Implement manual catalog entry**

Define the exact request contract:

```python
class ManualCatalogPart(BaseModel):
    part_num: str
    part_name: str
    color_id: int
    color_name: str
    rgb_hex: str
    quantity: int = Field(gt=0)
    is_spare: bool = False


class ManualCatalogSetCreate(BaseModel):
    set_num: str
    name: str
    year: int | None = None
    theme_name: str | None = None
    image_url: HttpUrl | None = None
    external_url: HttpUrl | None = None
    instructions_url: HttpUrl | None = None
    parts: list[ManualCatalogPart] = Field(min_length=1)
```

Manual import creates normal immutable catalog rows with `source="manual"`; later changes use local overrides.

- [ ] **Step 5: Add protected catalog routes and tests**

`GET /api/catalog/sets?q=&limit=20` searches set number and name case-insensitively. Import responses include counts, warnings, start/completion timestamps, and sync-run ID. Upload failures return `422` and leave the previous cache untouched.

- [ ] **Step 6: Run focused and full backend tests**

Run: `cd backend && uv run pytest tests/services/test_catalog_import.py tests/api/test_catalog.py -v && uv run pytest`

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: import official set catalogs from CSV or manual entry"
```

---

### Task 5: Targeted Rebrickable Lookup

**Files:**
- Create: `backend/app/services/rebrickable.py`
- Create: `backend/tests/services/test_rebrickable.py`
- Modify: `backend/app/api/catalog.py`
- Modify: `backend/app/schemas/catalog.py`
- Modify: `backend/tests/api/test_catalog.py`

**Interfaces:**
- Consumes: `Settings.rebrickable_api_key`, `httpx.Client`, catalog importer upsert primitives.
- Produces: `RebrickableClient.search_sets(query, limit) -> list[RemoteSetSummary]`, `RebrickableClient.lookup_set(set_num) -> ImportedSet`, `GET /api/catalog/remote-search`, `POST /api/catalog/lookup/{set_num}`, normalized `CatalogLookupError(code, message, retry_after)`.

- [ ] **Step 1: Write failing client tests with mocked HTTP responses**

```python
def test_lookup_fetches_set_and_all_part_pages(mock_transport):
    client = RebrickableClient("secret", transport=mock_transport)

    imported = client.lookup_set("75379-1")

    assert imported.set_num == "75379-1"
    assert len(imported.parts) == 101
    assert mock_transport.requests[1].url.params["inc_minifig_parts"] == "1"
    assert mock_transport.requests[2].url.params["page"] == "2"


def test_throttle_error_preserves_retry_after(mock_transport):
    mock_transport.respond(429, {"detail": "Expected available in 2 seconds."},
                           headers={"Retry-After": "2"})

    with pytest.raises(CatalogLookupError) as error:
        RebrickableClient("secret", transport=mock_transport).lookup_set("75379-1")

    assert error.value.code == "throttled"
    assert error.value.retry_after == 2


def test_remote_search_returns_summaries_without_importing(session, mock_transport):
    results = RebrickableClient("secret", transport=mock_transport).search_sets(
        "Galaxy Explorer", limit=20
    )

    assert results[0].set_num == "10497-1"
    assert session.get(CatalogSet, "10497-1") is None
```

- [ ] **Step 2: Verify the client tests fail**

Run: `cd backend && uv run pytest tests/services/test_rebrickable.py -v`

Expected: FAIL because `RebrickableClient` does not exist.

- [ ] **Step 3: Implement targeted lookup and mapping**

Call only:

```text
GET https://rebrickable.com/api/v3/lego/sets/?search={query}&page_size={limit}
GET https://rebrickable.com/api/v3/lego/sets/{set_num}/
GET https://rebrickable.com/api/v3/lego/sets/{set_num}/parts/?inc_minifig_parts=1&page_size=1000
```

Send `Authorization: key <api-key>`, follow the API's `next` links, use 10-second connect and 30-second read timeouts, and never log the authorization header. Map every returned part/color inline and persist the set plus inventory in one transaction. Replace only rows for that imported set after the complete response validates.

Map errors as follows: absent key `409 api_key_missing`, 404 `404 set_not_found`, 429 `429 rebrickable_throttled` with `retry_after`, timeout/network `503 rebrickable_unavailable`, malformed upstream data `502 invalid_upstream_response`.

- [ ] **Step 4: Add the protected targeted-lookup route**

`GET /api/catalog/remote-search?q=&limit=20` returns lightweight remote summaries and never mutates the cache. `POST /api/catalog/lookup/{set_num}` imports the selected result and returns the effective set plus a sync summary. Both return `409 api_key_missing` when lookup is disabled, and lookup must leave an existing cached set untouched on any remote or validation failure.

- [ ] **Step 5: Run lookup and catalog regression tests**

Run: `cd backend && uv run pytest tests/services/test_rebrickable.py tests/api/test_catalog.py -v`

Expected: all tests pass without live network calls.

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: add targeted Rebrickable set lookup"
```

---

### Task 6: Collection CRUD And Combined Inventory

**Files:**
- Create: `backend/app/schemas/collection.py`
- Create: `backend/app/schemas/inventory.py`
- Create: `backend/app/services/inventory.py`
- Create: `backend/app/api/collection.py`
- Create: `backend/app/api/inventory.py`
- Create: `backend/tests/services/test_inventory.py`
- Create: `backend/tests/api/test_collection.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `CatalogRepository.get_effective_set`, owned-set models, `require_auth`.
- Produces: collection CRUD routes; missing-piece CRUD routes; `compute_inventory(session) -> InventorySnapshot`; `GET /api/inventory`.

- [ ] **Step 1: Write failing inventory tests for quantity, spares, known missing pieces, and warnings**

```python
def test_inventory_expands_copies_includes_spares_and_subtracts_known_missing(session):
    seed_set_with_parts(session, "1234-1", [
        ("3001", 5, 2, False),
        ("6141", 1, 1, True),
    ])
    owned = seed_owned_set(session, "1234-1", quantity=2, completeness="incomplete")
    seed_missing_part(session, owned.id, "3001", 5, quantity=1)

    snapshot = compute_inventory(session)

    assert snapshot.quantity("3001", 5) == 3
    assert snapshot.quantity("6141", 1) == 2


def test_unknown_missing_note_warns_without_changing_math(session):
    seed_set_with_parts(session, "1234-1", [("3001", 5, 2, False)])
    seed_owned_set(session, "1234-1", quantity=1, completeness="incomplete",
                   unknown_missing_count=3, unknown_missing_note="A few tiny pieces")

    snapshot = compute_inventory(session)

    assert snapshot.quantity("3001", 5) == 2
    assert snapshot.warnings[0].set_num == "1234-1"
```

- [ ] **Step 2: Verify inventory tests fail**

Run: `cd backend && uv run pytest tests/services/test_inventory.py -v`

Expected: FAIL because `compute_inventory` is undefined.

- [ ] **Step 3: Implement the inventory snapshot contract**

```python
@dataclass(frozen=True)
class InventoryItem:
    part_num: str
    part_name: str
    color_id: int
    color_name: str
    rgb_hex: str
    quantity: int
    image_url: str | None
    source_set_nums: tuple[str, ...]


@dataclass(frozen=True)
class InventoryWarning:
    owned_set_id: int
    set_num: str
    set_name: str
    unknown_missing_count: int | None
    note: str | None


@dataclass(frozen=True)
class InventorySnapshot:
    items: tuple[InventoryItem, ...]
    warnings: tuple[InventoryWarning, ...]
    total_quantity: int

    def quantity(self, part_num: str, color_id: int) -> int:
        return next(
            (item.quantity for item in self.items
             if item.part_num == part_num and item.color_id == color_id),
            0,
        )
```

Expand every effective catalog row, including spares, by owned quantity. Subtract each known missing row exactly once from the aggregate and clamp at zero while reporting an integrity warning if recorded missing quantity exceeds expected quantity. Unknown missing data only adds `InventoryWarning`.

- [ ] **Step 4: Implement collection and missing-piece API contracts**

Routes:

```text
GET    /api/collection
POST   /api/collection
PATCH  /api/collection/{owned_set_id}
DELETE /api/collection/{owned_set_id}
GET    /api/collection/{owned_set_id}/missing-parts
POST   /api/collection/{owned_set_id}/missing-parts
PATCH  /api/collection/{owned_set_id}/missing-parts/{missing_id}
DELETE /api/collection/{owned_set_id}/missing-parts/{missing_id}
GET    /api/inventory?q=&color_id=&offset=0&limit=100
```

Adding a set requires an existing catalog set, quantity `>=1`, and unique owned row per `set_num`; adding an existing set increments quantity. Missing quantities must not exceed the owned set's effective expected quantity across all copies. Collection responses include set metadata, completeness, notes, known-missing total, unknown warning, and `has_local_overrides`.

- [ ] **Step 5: Add API tests for all CRUD and validation paths**

Assert authentication, increment-on-duplicate, quantity edits, known-missing limits, delete cascade, search, color filter, pagination, and warning serialization.

- [ ] **Step 6: Run focused and full backend tests**

Run: `cd backend && uv run pytest tests/services/test_inventory.py tests/api/test_collection.py -v && uv run pytest`

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: manage owned sets and compute available inventory"
```

---

### Task 7: Explainable Buildability Matcher

**Files:**
- Create: `backend/app/services/matcher.py`
- Create: `backend/tests/services/test_matcher.py`

**Interfaces:**
- Consumes: `InventorySnapshot`, target `EffectivePartRow` rows, equivalence map `dict[str, frozenset[str]]`.
- Produces: `match_set(target: EffectiveSet, inventory: InventorySnapshot, equivalents: Mapping[str, frozenset[str]]) -> MatchResult`.

- [ ] **Step 1: Write the matcher test matrix before implementation**

```python
@pytest.mark.parametrize(
    ("available", "required", "status", "exact", "color", "equivalent", "missing"),
    [
        ([item("3001", 5, 2)], [row("3001", 5, 2)], "exact", 2, 0, 0, 0),
        ([item("3001", 1, 2)], [row("3001", 5, 2)], "substitution", 0, 2, 0, 0),
        ([item("3002", 5, 2)], [row("3001", 5, 2)], "substitution", 0, 0, 2, 0),
        ([item("3001", 5, 1)], [row("3001", 5, 2)], "missing", 1, 0, 0, 1),
    ],
)
def test_match_statuses(available, required, status, exact, color, equivalent, missing):
    result = match_set(target(required), snapshot(available), {"3001": frozenset({"3002"})})

    assert result.status == status
    assert (result.exact_quantity, result.color_substitution_quantity,
            result.equivalence_substitution_quantity, result.missing_quantity) == (
                exact, color, equivalent, missing
            )
```

Add named tests proving: exact matches are consumed before color substitutions; same-color equivalent matches precede any-color equivalent matches; one available piece cannot satisfy two requirements; target spares are ignored; quantities aggregate across colors; percentages use required quantity as denominator; empty target is rejected.

- [ ] **Step 2: Run matcher tests to verify they fail**

Run: `cd backend && uv run pytest tests/services/test_matcher.py -v`

Expected: FAIL because matcher types and function do not exist.

- [ ] **Step 3: Implement immutable matcher result types**

```python
@dataclass(frozen=True)
class MatchAllocation:
    required_part_num: str
    required_color_id: int
    supplied_part_num: str
    supplied_color_id: int
    quantity: int
    kind: Literal["exact", "color", "equivalent_exact_color", "equivalent_color"]


@dataclass(frozen=True)
class MissingRequirement:
    part_num: str
    part_name: str
    color_id: int
    color_name: str
    quantity: int


@dataclass(frozen=True)
class MatchResult:
    status: Literal["exact", "substitution", "missing"]
    required_quantity: int
    exact_quantity: int
    color_substitution_quantity: int
    equivalence_substitution_quantity: int
    missing_quantity: int
    percent_exact: float
    percent_buildable: float
    allocations: tuple[MatchAllocation, ...]
    missing: tuple[MissingRequirement, ...]
```

- [ ] **Step 4: Implement deterministic four-pass consumption**

Copy inventory quantities into a mutable local map; never mutate `InventorySnapshot`. Normalize target rows by `(part_num, color_id)` excluding `is_spare`. For each requirement, allocate in this order: exact part/color, same part other colors sorted by available quantity descending then color ID, equivalent parts exact color sorted by part number, equivalent parts other colors sorted by available quantity descending then part/color. Record every allocation and decrement the local map.

Set status to `missing` when missing quantity is nonzero, else `substitution` when any non-exact allocation exists, else `exact`. Round percentages to one decimal.

- [ ] **Step 5: Run matcher tests and backend regression suite**

Run: `cd backend && uv run pytest tests/services/test_matcher.py -v && uv run pytest`

Expected: matcher matrix and all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/matcher.py backend/tests/services/test_matcher.py
git commit -m "feat: add color-tolerant buildability matcher"
```

---

### Task 8: Target Match And Recommendation APIs

**Files:**
- Create: `backend/app/schemas/matches.py`
- Create: `backend/app/services/recommendations.py`
- Create: `backend/app/api/matches.py`
- Create: `backend/app/api/recommendations.py`
- Create: `backend/tests/api/test_matches.py`
- Create: `backend/tests/api/test_recommendations.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `compute_inventory`, `match_set`, effective catalog repository, equivalence members, owned sets.
- Produces: `GET /api/matches/{set_num}` and `GET /api/recommendations`.

- [ ] **Step 1: Write failing target-detail and recommendation tests**

```python
def test_target_match_serializes_color_story(client, authenticated, seeded_collection):
    response = client.get("/api/matches/5678-1")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "substitution"
    assert body["counts"]["color_substitution"] == 2
    assert body["substitutions"][0]["required_color"]["name"] == "Red"
    assert body["substitutions"][0]["supplied_color"]["name"] == "Blue"


def test_recommendations_default_to_not_owned_and_within_piece_threshold(
    client, authenticated, seeded_collection
):
    response = client.get("/api/recommendations")

    assert response.status_code == 200
    assert [item["set_num"] for item in response.json()["items"]] == ["1000-1", "1001-1"]
    assert all(item["num_parts"] <= seeded_collection.total_quantity for item in response.json()["items"])
```

- [ ] **Step 2: Verify the API tests fail**

Run: `cd backend && uv run pytest tests/api/test_matches.py tests/api/test_recommendations.py -v`

Expected: FAIL with 404 routes.

- [ ] **Step 3: Implement match-detail serialization**

Return target metadata, result counts, percentages, grouped substitutions, missing requirements, inventory confidence warnings, `has_local_overrides`, and external/instruction links. Group allocations with the same required and supplied identity so the frontend receives one inspectable row per substitution story.

- [ ] **Step 4: Implement bounded recommendation evaluation**

Contract:

```text
GET /api/recommendations
  ?status=exact,substitution,missing
  &max_pieces=<int>
  &theme=<string>
  &year_from=<int>
  &year_to=<int>
  &hide_owned=true
  &sort=buildability|pieces|year|mismatches|missing
  &direction=asc|desc
  &offset=0
  &limit=50
```

Default `max_pieces` to `InventorySnapshot.total_quantity`, default `hide_owned=true`, and cap `limit` at 100. First select candidate set numbers with SQL filters, then match candidates locally. Default order is status rank exact/substitution/missing, missing quantity ascending, substitution quantity ascending, set number ascending. Return `total_candidates`, pagination values, active defaults, and compact counts per item.

- [ ] **Step 5: Add tests for filters, sorts, pagination, and empty inventory**

Cover each sort, status filter, theme/year intersection, explicit threshold disable (`max_pieces=0` means no threshold), owned visibility, stable pagination, and zero-collection response.

- [ ] **Step 6: Run API and full backend suites**

Run: `cd backend && uv run pytest tests/api/test_matches.py tests/api/test_recommendations.py -v && uv run pytest`

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: expose build matches and recommendations"
```

---

### Task 9: Local Corrections And Equivalence Groups

**Files:**
- Create: `backend/app/schemas/settings.py`
- Create: `backend/app/api/overrides.py`
- Create: `backend/app/api/equivalence.py`
- Create: `backend/tests/api/test_overrides.py`
- Create: `backend/tests/api/test_equivalence.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: override/equivalence models, `CatalogRepository`, match APIs.
- Produces: CRUD routes for set metadata overrides, set-part overrides, and equivalence groups; `load_equivalence_map(session) -> dict[str, frozenset[str]]`.

- [ ] **Step 1: Write failing tests proving corrections are visible and equivalence changes matching**

```python
def test_inventory_override_changes_effective_set_without_mutating_import(client, session, authenticated):
    response = client.put("/api/overrides/sets/1234-1/parts/3001/5", json={
        "operation": "upsert", "quantity": 4, "is_spare": False,
        "reason": "Counted from instructions"
    })

    assert response.status_code == 200
    assert response.json()["has_local_overrides"] is True
    assert session.get(CatalogSetPart, imported_row_id).quantity == 2


def test_equivalence_group_turns_missing_result_into_substitution(client, authenticated):
    before = client.get("/api/matches/5678-1").json()
    client.post("/api/equivalence-groups", json={
        "name": "1x2 jumper variants", "part_nums": ["15573", "3794b"], "notes": None
    })
    after = client.get("/api/matches/5678-1").json()

    assert before["status"] == "missing"
    assert after["status"] == "substitution"
```

- [ ] **Step 2: Verify correction tests fail**

Run: `cd backend && uv run pytest tests/api/test_overrides.py tests/api/test_equivalence.py -v`

Expected: FAIL with missing routes.

- [ ] **Step 3: Implement explicit correction APIs**

Routes:

```text
PUT    /api/overrides/sets/{set_num}
DELETE /api/overrides/sets/{set_num}
PUT    /api/overrides/sets/{set_num}/parts/{part_num}/{color_id}
DELETE /api/overrides/sets/{set_num}/parts/{part_num}/{color_id}
GET    /api/overrides/sets/{set_num}
```

Every write requires a non-empty reason. The request always includes `is_spare` as part of the corrected row identity. Upsert inventory rows require `quantity >= 1`; delete operations require `quantity=null`. Responses include imported value, override value, and effective value so the local layer is visible.

- [ ] **Step 4: Implement equivalence-group CRUD and map loading**

Routes:

```text
GET    /api/equivalence-groups
POST   /api/equivalence-groups
PUT    /api/equivalence-groups/{group_id}
DELETE /api/equivalence-groups/{group_id}
```

Require a unique name and at least two distinct existing catalog part numbers. A part may belong to only one group in V1; return `409 part_already_grouped` on conflict. `load_equivalence_map()` maps every member to all other members in its group.

- [ ] **Step 5: Run correction, matcher, and inventory regression tests**

Run: `cd backend && uv run pytest tests/api/test_overrides.py tests/api/test_equivalence.py tests/services/test_matcher.py tests/services/test_inventory.py -v`

Expected: all tests pass and imported rows remain unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: layer local corrections and part equivalences"
```

---

### Task 10: Versioned Backup, Restore, And Operational Status

**Files:**
- Create: `backend/app/schemas/backup.py`
- Create: `backend/app/services/backup.py`
- Create: `backend/app/api/backups.py`
- Create: `backend/app/api/settings.py`
- Create: `backend/tests/services/test_backup.py`
- Create: `backend/tests/api/test_settings.py`
- Modify: `backend/app/cli.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: collection, missing, override, equivalence, app-setting, and sync-run models.
- Produces: `export_backup(session) -> BackupV1`, `restore_backup(session, backup, mode) -> RestoreSummary`; backup export/import routes; settings status route; CLI `what2build export-backup PATH`.

- [ ] **Step 1: Write failing backup round-trip and secret-exclusion tests**

```python
def test_backup_round_trip_preserves_personal_data(source_session, catalog_seeded_session):
    seed_personal_data(source_session)

    payload = export_backup(source_session).model_dump(mode="json")
    result = restore_backup(
        catalog_seeded_session, BackupV1.model_validate(payload), mode="replace"
    )
    restored = export_backup(catalog_seeded_session).model_dump(mode="json")

    assert result.owned_sets == 2
    assert {k: v for k, v in restored.items() if k != "exported_at"} == {
        k: v for k, v in payload.items() if k != "exported_at"
    }


def test_backup_excludes_secrets(session):
    seed_setting(session, "auth.password_hash", "hash", secret=True)
    seed_setting(session, "rebrickable_api_key", "secret", secret=True)
    seed_setting(session, "ui.default_sort", "buildability", secret=False)

    serialized = export_backup(session).model_dump_json()

    assert "auth.password_hash" not in serialized
    assert "rebrickable_api_key" not in serialized
    assert "ui.default_sort" in serialized
```

Add tests for unsupported schema version, dangling set/part references, replace rollback, and merge conflict reporting.

- [ ] **Step 2: Verify backup tests fail**

Run: `cd backend && uv run pytest tests/services/test_backup.py -v`

Expected: FAIL because backup services do not exist.

- [ ] **Step 3: Define and implement `what2build.backup/v1`**

Top-level JSON fields are exactly:

```json
{
  "schema": "what2build.backup/v1",
  "exported_at": "2026-08-10T12:00:00Z",
  "owned_sets": [],
  "missing_parts": [],
  "set_overrides": [],
  "set_part_overrides": [],
  "equivalence_groups": [],
  "settings": {}
}
```

Export only `app_settings.secret = false`. Catalog cache is deliberately absent; validate that every referenced set, part, and color already exists before any writes and return a structured list of missing dependencies so the user can import/refresh the catalog first. `replace` deletes and recreates only personal collection/rule/settings data inside one transaction; it leaves imported catalog and sync history untouched. `merge` upserts by stable natural keys, reports changed/skipped/conflicting counts, and rejects ambiguous duplicate inputs.

- [ ] **Step 4: Implement intentional restore and safety backup flow**

Routes:

```text
GET  /api/backups/export
POST /api/backups/validate
POST /api/backups/import?mode=replace|merge&confirm=true
GET  /api/settings/status
```

Before replace, write a timestamped safety JSON file beneath `${data_dir}/backups/`; if that write fails, abort the restore. Return the safety-backup filename in `RestoreSummary`. `GET /api/settings/status` returns API-key configured boolean, last successful import, latest failed import, catalog counts, database path label (not absolute secret-bearing path), and current backup schema.

Add `what2build export-backup PATH`, which refuses to overwrite an existing file, creates missing parent directories for the explicit path, writes UTF-8 JSON atomically, and prints only the final path and exported record counts.

- [ ] **Step 5: Run backup/settings and full backend tests**

Run: `cd backend && uv run pytest tests/services/test_backup.py tests/api/test_settings.py -v && uv run pytest`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: add versioned backup restore and status APIs"
```

---

### Task 11: Workshop Rail Shell And Unlock Screen

**Files:**
- Create: `frontend/src/lib/api/types.ts`
- Create: `frontend/src/lib/api/client.ts`
- Create: `frontend/src/lib/stores/session.svelte.ts`
- Create: `frontend/src/lib/components/shell/AppShell.svelte`
- Create: `frontend/src/lib/components/shell/WorkshopRail.svelte`
- Create: `frontend/src/lib/components/shell/MobileNav.svelte`
- Create: `frontend/src/lib/components/shell/StatusStud.svelte`
- Create: `frontend/src/lib/components/shell/AppShell.test.ts`
- Create: `frontend/src/routes/unlock/+page.svelte`
- Modify: `frontend/src/routes/+layout.svelte`
- Modify: `frontend/src/routes/+page.svelte`
- Modify: `frontend/src/app.css`

**Interfaces:**
- Consumes: auth API routes.
- Produces: `apiFetch<T>()`, reactive `session`, authenticated shell, navigation routes, and unlock form.

- [ ] **Step 1: Write failing shell and unlock component tests**

```typescript
it('shows the workshop navigation after authentication', async () => {
  mockApi.session({ authenticated: true });
  render(AppShell, { props: { pathname: '/inventory', children: snippet } });

  expect(screen.getByRole('navigation', { name: 'Primary' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Inventory' })).toHaveAttribute('aria-current', 'page');
});

it('submits the password and redirects to the requested screen', async () => {
  mockApi.login({ status: 204 });
  render(UnlockPage);

  await userEvent.type(screen.getByLabelText('Shared password'), 'build-stuff');
  await userEvent.click(screen.getByRole('button', { name: 'Unlock' }));

  expect(mockApi.lastRequest()).toMatchObject({ url: '/api/auth/login', method: 'POST' });
});
```

- [ ] **Step 2: Verify frontend tests fail**

Run: `cd frontend && npm test -- AppShell.test.ts`

Expected: FAIL because the shell components do not exist.

- [ ] **Step 3: Implement the typed API client and session state**

`apiFetch<T>(path, options)` must set `credentials: 'include'`, JSON encode object bodies, parse structured API errors into `ApiError {status, code, message}`, and redirect to `/unlock?next=<path>` on 401 except for auth calls. Session state exposes `load()`, `login(password)`, `logout()`, `authenticated`, and `loading`.

- [ ] **Step 4: Implement the approved visual shell**

Use an off-white work surface, near-black ink, LEGO red for active navigation, yellow for caution/substitution, blue for informational actions, and green only for exact success. Define CSS custom properties and focused components rather than a utility framework. Desktop uses a stable 224px rail and content column; mobile below 720px uses a 56px bottom navigation with icon-only secondary actions and tooltips.

Navigation labels are Collection, Inventory, Buildable Sets, and Settings using lucide icons. `StatusStud` is a 10px square/circle-like stud mark with icon/accessible text, not a text pill. Keep cards at 8px radius or less and avoid gradients, decorative blobs, nested cards, and marketing copy.

- [ ] **Step 5: Implement unlock behavior and route guard**

Show a compact branded `What2Build` wordmark, one password field, Unlock button, and inline error. Preserve `next` only when it is a local path beginning with `/`. The root route redirects authenticated users to `/buildable` and unauthenticated users to `/unlock`.

- [ ] **Step 6: Run shell tests, type checks, and responsive component inspection**

Run:

```bash
cd frontend
npm test -- AppShell.test.ts
npm run check
npm run build
```

Expected: tests and checks pass; no horizontal overflow at 390px in the component test viewport.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "feat: add Workshop Rail shell and unlock flow"
```

---

### Task 12: Collection And Inventory Screens

**Files:**
- Create: `frontend/src/lib/components/collection/OwnedSetRow.svelte`
- Create: `frontend/src/lib/components/collection/OwnedSetDialog.svelte`
- Create: `frontend/src/lib/components/collection/MissingPartsEditor.svelte`
- Create: `frontend/src/lib/components/inventory/InventoryLedger.svelte`
- Create: `frontend/src/lib/components/inventory/InventoryRow.svelte`
- Create: `frontend/src/lib/components/inventory/ConfidenceNotice.svelte`
- Create: `frontend/src/routes/collection/+page.svelte`
- Create: `frontend/src/routes/inventory/+page.svelte`
- Create: `frontend/src/routes/collection/collection.test.ts`
- Create: `frontend/src/routes/inventory/inventory.test.ts`

**Interfaces:**
- Consumes: catalog search, collection CRUD, missing-part CRUD, and inventory APIs.
- Produces: complete collection management and Inventory Ledger workflows.

- [ ] **Step 1: Write failing interaction tests for the two screens**

```typescript
it('adds a cached set and records a known missing piece', async () => {
  render(CollectionPage);
  await userEvent.click(screen.getByRole('button', { name: 'Add set' }));
  await userEvent.type(screen.getByLabelText('Set number or name'), 'Galaxy Explorer');
  await userEvent.click(await screen.findByRole('option', { name: /10497-1 Galaxy Explorer/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Add to collection' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Edit missing pieces' }));
  await userEvent.click(screen.getByRole('button', { name: /Plate 1 x 2, Red/ }));
  await userEvent.clear(screen.getByLabelText('Missing quantity'));
  await userEvent.type(screen.getByLabelText('Missing quantity'), '2');
  await userEvent.click(screen.getByRole('button', { name: 'Save missing piece' }));

  expect(await screen.findByText('2 known missing')).toBeInTheDocument();
});

it('expands an inventory part into color rows', async () => {
  render(InventoryPage);
  await userEvent.click(await screen.findByRole('button', { name: 'Expand Brick 2 x 4' }));

  expect(screen.getByText('Bright Red')).toBeInTheDocument();
  expect(screen.getByText('Dark Bluish Gray')).toBeInTheDocument();
});
```

- [ ] **Step 2: Verify screen tests fail**

Run: `cd frontend && npm test -- collection.test.ts inventory.test.ts`

Expected: FAIL because screen components do not exist.

- [ ] **Step 3: Build the Collection screen**

Use a dense list with set thumbnail, set number/name, quantity stepper, completeness toggle, known-missing count, warning mark, and overflow menu for edit/remove. `OwnedSetDialog` searches cached catalog after 250ms debounce, then offers remote name/number results when an API key is configured; selecting a remote result performs targeted import before adding it. Without an API key, the no-result state links directly to manual/ZIP import. The missing editor searches expected rows for that owned set and uses part thumbnail, color swatch, quantity input, and note.

Removal requires a confirmation dialog naming the set. Incomplete status reveals unknown count/note inputs; changing back to complete asks whether to clear unknown warning data but preserves known missing rows unless explicitly removed.

- [ ] **Step 4: Build the Inventory Ledger screen**

Group API items by part number. Desktop columns: part, total, colors, source sets; expanding a row shows color swatch/name, quantity, and source-set numbers. Mobile turns each ledger row into an unframed stacked block while preserving the expansion control. Include search, color menu, total part quantity, unique part count, and `ConfidenceNotice` listing incomplete owned sets without reducing totals.

- [ ] **Step 5: Run component tests and frontend verification**

Run:

```bash
cd frontend
npm test -- collection.test.ts inventory.test.ts
npm run check
npm run build
```

Expected: tests, type checks, and build pass.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat: add collection and inventory workflows"
```

---

### Task 13: Buildable Sets And Builder's Bench Detail

**Files:**
- Create: `frontend/src/lib/components/matches/MatchMeter.svelte`
- Create: `frontend/src/lib/components/matches/RecommendationRow.svelte`
- Create: `frontend/src/lib/components/matches/RecommendationFilters.svelte`
- Create: `frontend/src/lib/components/matches/SubstitutionStory.svelte`
- Create: `frontend/src/lib/components/matches/MissingPartsTable.svelte`
- Create: `frontend/src/routes/buildable/+page.svelte`
- Create: `frontend/src/routes/sets/[set_num]/+page.svelte`
- Create: `frontend/src/routes/buildable/buildable.test.ts`
- Create: `frontend/src/routes/sets/set-detail.test.ts`

**Interfaces:**
- Consumes: recommendation and target-match APIs.
- Produces: cached-set discovery, search, filtering, and inspectable match details.

- [ ] **Step 1: Write failing recommendation and detail tests**

```typescript
it('shows exact sets before color-substitution sets and can reveal missing sets', async () => {
  render(BuildablePage);

  const rows = await screen.findAllByRole('article');
  expect(within(rows[0]).getByText('Exact build')).toBeInTheDocument();
  expect(within(rows[1]).getByText('Buildable with color swaps')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('checkbox', { name: 'Missing pieces' }));
  expect(await screen.findByText('Missing 3')).toBeInTheDocument();
});

it('explains required and supplied colors in Builder Bench detail', async () => {
  render(SetDetailPage);

  expect(await screen.findByRole('heading', { name: /Galaxy Explorer/ })).toBeInTheDocument();
  expect(screen.getByText('Needs Bright Red')).toBeInTheDocument();
  expect(screen.getByText('Use Dark Blue')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Instructions' })).toHaveAttribute('target', '_blank');
});
```

- [ ] **Step 2: Verify match-screen tests fail**

Run: `cd frontend && npm test -- buildable.test.ts set-detail.test.ts`

Expected: FAIL because match components do not exist.

- [ ] **Step 3: Build the recommendation workspace**

Place a literal target search at the top, followed by a compact results toolbar. Search cached sets first and include remote name/number results when API lookup is configured; selecting one imports it and opens its match detail. Filters use checkboxes for statuses, menus for theme/year/sort, and a numeric maximum-pieces input initialized from the API default. Recommendation rows show actual set image, set identity, year/theme, stable-width match meter, exact/substitution/missing counts, and a right-arrow icon button with tooltip. Do not use a decorative card grid; use an efficient list on desktop and one repeated compact item per set on mobile.

Fetch on filter changes with `AbortController`, preserve filters in URL query parameters, and display non-blocking retry controls for API/network errors.

- [ ] **Step 4: Build the Builder's Bench detail screen**

The first viewport shows actual set image, set name/number, status, match meter, counts, confidence warning, and instruction/external links. Below, use tabs for Color swaps, Equivalent parts, and Missing pieces; each row displays required part/color beside supplied part/color with real swatches and quantities. Hide empty tabs and show an exact-build completion state without celebratory marketing copy.

Local-correction status is visible beside metadata. Missing rows include part image, identity, required color, and quantity. Never imply that viewing the set reserves inventory.

- [ ] **Step 5: Run frontend tests and responsive build verification**

Run:

```bash
cd frontend
npm test -- buildable.test.ts set-detail.test.ts
npm run check
npm run build
```

Expected: all tests pass and meter/toolbar dimensions do not shift between statuses.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat: add buildable discovery and match detail screens"
```

---

### Task 14: Settings, Imports, Corrections, And Backups UI

**Files:**
- Create: `frontend/src/lib/components/settings/CatalogImportPanel.svelte`
- Create: `frontend/src/lib/components/settings/BackupPanel.svelte`
- Create: `frontend/src/lib/components/settings/EquivalenceEditor.svelte`
- Create: `frontend/src/lib/components/settings/CorrectionEditor.svelte`
- Create: `frontend/src/routes/settings/+page.svelte`
- Create: `frontend/src/routes/settings/settings.test.ts`

**Interfaces:**
- Consumes: settings status, CSV/manual import, overrides, equivalence, backup, and password APIs.
- Produces: operational/settings workflow with explicit destructive confirmations.

- [ ] **Step 1: Write failing settings interaction tests**

```typescript
it('validates a restore before enabling replace', async () => {
  render(SettingsPage);
  const file = new File([validBackupJson], 'what2build-backup.json', { type: 'application/json' });

  await userEvent.upload(screen.getByLabelText('Backup file'), file);
  expect(await screen.findByText('2 owned sets, 1 equivalence group')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Replace local data' })).toBeEnabled();
});

it('creates an explicit equivalence group', async () => {
  render(SettingsPage);
  await userEvent.click(screen.getByRole('button', { name: 'New equivalence group' }));
  await userEvent.type(screen.getByLabelText('Group name'), 'Jumper variants');
  await choosePart('15573');
  await choosePart('3794b');
  await userEvent.click(screen.getByRole('button', { name: 'Save group' }));

  expect(await screen.findByText('Jumper variants')).toBeInTheDocument();
});
```

- [ ] **Step 2: Verify settings tests fail**

Run: `cd frontend && npm test -- settings.test.ts`

Expected: FAIL because settings components do not exist.

- [ ] **Step 3: Build catalog and correction controls**

Show API-key configured status without ever accepting or displaying the key. ZIP import uses file picker, progress state, success counts, warnings, and last successful/failed import. Manual set entry is a focused dialog with metadata plus editable inventory rows. Corrections are reached from a set and compare imported, local, and effective values; each save requires a reason.

- [ ] **Step 4: Build backup, password, and equivalence controls**

Export uses a download icon button and server-provided filename. Import first calls validation; missing catalog dependencies keep restore disabled and link to catalog import. A valid backup presents mutually exclusive Merge and Replace options; Replace requires typing `REPLACE` and states the safety-backup filename after success. Password change asks for current/new/confirm and logs out all prior sessions. Equivalence groups use searchable part pickers, at least two members, and clear conflict messages.

- [ ] **Step 5: Document the approved future work without shipping inactive UI**

Create `docs/product/future-features.md` with sections for multi-set build planning/reservations, loose-piece inventory, storage/tags/loans, build history/current builds, scheduled catalog sync, MOCs/alternate builds, household users, richer substitution rules, stored instruction/build-session tools, and scanner work. The scanner section specifies camera/barcode/QR quick-add entry from Collection/Search, permission handling, manual confirmation, and part-recognition uncertainty. Do not add disabled future-feature buttons or feature-description copy to the running app.

- [ ] **Step 6: Run settings tests and all frontend checks**

Run:

```bash
cd frontend
npm test
npm run check
npm run build
```

Expected: all frontend tests and build pass.

- [ ] **Step 7: Commit**

```bash
git add frontend docs/product/future-features.md
git commit -m "feat: add catalog settings corrections and backup UI"
```

---

### Task 15: Production Serving, Raspberry Pi Deployment, And End-To-End Acceptance

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/app.spec.ts`
- Create: `frontend/e2e/mobile.spec.ts`
- Create: `Dockerfile`
- Create: `compose.yaml`
- Create: `.dockerignore`
- Create: `.env.example`
- Create: `scripts/reset-password.sh`
- Create: `README.md`
- Modify: `backend/app/main.py`
- Modify: `backend/app/config.py`

**Interfaces:**
- Consumes: complete API and static frontend build.
- Produces: one production image/process, persistent `/data`, reset procedure, health check, and acceptance-level browser tests.

- [ ] **Step 1: Write the end-to-end acceptance test before production wiring**

```typescript
test('owned sets become an explainable buildable recommendation', async ({ page, request }) => {
  await seedCatalogAndPassword(request);
  await page.goto('/unlock');
  await page.getByLabel('Shared password').fill('build-stuff');
  await page.getByRole('button', { name: 'Unlock' }).click();

  await page.getByRole('link', { name: 'Collection' }).click();
  await page.getByRole('button', { name: 'Add set' }).click();
  await page.getByLabel('Set number or name').fill('10497-1');
  await page.getByRole('option', { name: /10497-1/ }).click();
  await page.getByRole('button', { name: 'Add to collection' }).click();

  await page.getByRole('link', { name: 'Buildable Sets' }).click();
  await expect(page.getByText('Buildable with color swaps').first()).toBeVisible();
  await page.getByRole('article').filter({ hasText: 'Buildable with color swaps' }).first().click();
  await expect(page.getByText(/Needs .* Use/).first()).toBeVisible();
});
```

Add a second test that records a known missing piece and verifies inventory decreases, plus a 390x844 mobile test that navigates every primary screen and asserts `document.documentElement.scrollWidth === window.innerWidth`.

- [ ] **Step 2: Run E2E to verify production wiring is absent**

Run: `cd frontend && npx playwright test e2e/app.spec.ts --project=chromium`

Expected: FAIL because the integrated web server/static serving is not configured.

- [ ] **Step 3: Serve the static Svelte app from FastAPI**

When `Settings.frontend_dir` exists, mount immutable assets under `/_app` and add a final SPA fallback route that returns `index.html` for non-`/api` paths. Never let the fallback intercept `/api/*`; unknown API paths remain JSON 404. Set cache headers to one year for fingerprinted `/_app` files and `no-cache` for `index.html`.

- [ ] **Step 4: Build the multi-stage ARM64-compatible image and Compose service**

```dockerfile
FROM node:22-bookworm-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.10.3 /uv /uvx /bin/
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./alembic.ini
COPY --from=frontend /src/frontend/build ./static
ENV PATH="/app/.venv/bin:$PATH" WHAT2BUILD_DATA_DIR=/data WHAT2BUILD_FRONTEND_DIR=/app/static
EXPOSE 8000
CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]
```

`compose.yaml` builds the image, maps `${WHAT2BUILD_PORT:-8000}:8000`, mounts `./data:/data`, sets `WHAT2BUILD_DATABASE_URL=sqlite:////data/what2build.db`, requires `${WHAT2BUILD_SESSION_SECRET:?set WHAT2BUILD_SESSION_SECRET}`, loads `.env`, restarts unless stopped, and health-checks `/api/health`. `.env.example` contains generated-value instructions for `WHAT2BUILD_SESSION_SECRET`, bootstrap `WHAT2BUILD_INITIAL_PASSWORD`, optional `WHAT2BUILD_REBRICKABLE_API_KEY`, `WHAT2BUILD_SECURE_COOKIES=false`, and port.

- [ ] **Step 5: Add first-run password bootstrap and reset script**

On startup, if no password hash exists, require `WHAT2BUILD_INITIAL_PASSWORD`, hash it once, persist it, and never log it. If neither persisted hash nor initial password exists, fail startup with a clear message. Add `what2build reset-password --stdin`, which reads and confirms two lines from standard input. `scripts/reset-password.sh` prompts silently twice, rejects mismatches locally, and pipes the confirmed value to `docker compose exec -T app what2build reset-password --stdin`; it never puts the password in shell history or process arguments.

- [ ] **Step 6: Write operational documentation**

README commands must cover:

```bash
make dev
make test
make check
docker compose up --build -d
docker compose logs -f app
./scripts/reset-password.sh
docker compose exec app what2build export-backup /data/backups/manual.json
```

Document macOS prerequisites, 64-bit Raspberry Pi OS/Debian 12+, LAN URL, data directory ownership, API-key setup, ZIP import contents, manual import, backup/restore, upgrade procedure (`docker compose build && docker compose up -d`), and recovery by restoring the `data/` directory. For JSON-only recovery, explicitly import the catalog first and then restore personal data. Include the Future Work document link.

- [ ] **Step 7: Run complete verification from clean builds**

Run:

```bash
make test
make check
docker compose build
docker compose up -d
curl --fail http://localhost:8000/api/health
cd frontend && npx playwright test --project=chromium
cd .. && docker compose down
git diff --check
```

Expected: backend/frontend tests pass, static build succeeds, ARM-compatible Docker image builds, health returns `{"status":"ok"}`, desktop/mobile E2E tests pass, and Git reports no whitespace errors.

- [ ] **Step 8: Visually verify desktop and mobile layouts**

Capture Playwright screenshots at 1280x800 and 390x844 for unlock, collection, inventory, buildable list, match detail, and settings. Check real set images are legible, swatches remain distinguishable with text labels, no controls overlap, no text clips, the mobile nav does not cover content, and the next content region remains visible without oversized headings. Fix any failure and rerun the affected screenshot/test.

- [ ] **Step 9: Commit**

```bash
git add Dockerfile compose.yaml .dockerignore .env.example scripts README.md backend frontend
git commit -m "feat: ship Raspberry Pi deployment and acceptance tests"
```

---

## Implementation References

- Svelte's official package directory identifies SvelteKit as the official router, `adapter-static` as the static adapter, and Vitest/Playwright as supported CLI add-ons: <https://svelte.dev/packages>
- FastAPI's official testing guide uses `TestClient` with pytest and HTTPX: <https://fastapi.tiangolo.com/tutorial/testing/>
- SQLAlchemy's official 2.0 documentation covers typed ORM mappings and SQLite URLs: <https://docs.sqlalchemy.org/en/20/orm/> and <https://docs.sqlalchemy.org/en/20/core/engines.html#sqlite>
- Rebrickable's V3 documentation requires an API key, recommends CSV downloads for bulk data, documents throttling, and supports `inc_minifig_parts=1`: <https://rebrickable.com/api/v3/docs/?key=xxxxxxxxxx>
- Playwright's official guidance favors user-visible locators and isolated tests: <https://playwright.dev/docs/locators> and <https://playwright.dev/docs/best-practices>
