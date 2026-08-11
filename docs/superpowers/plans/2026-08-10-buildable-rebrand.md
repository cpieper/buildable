# Buildable Rebrand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all tracked legacy product, runtime, deployment, backup, and documentation identifiers with Buildable.

**Architecture:** Perform a clean, intentional runtime rename instead of a compatibility layer: user-facing copy becomes `Buildable`, the Python distribution/CLI becomes `buildable`, and runtime configuration becomes `BUILDABLE_*`. The backup wire identifier, cookie name, database filename, Docker/Compose configuration, fixtures, and docs move together so the installed system has one coherent identity.

**Tech Stack:** FastAPI, Pydantic Settings, SQLAlchemy/Alembic, Python/uv, SvelteKit, Vitest, Playwright, Docker Compose.

## Global Constraints

- Rename every tracked, case-insensitive legacy runtime or product reference to its `buildable` equivalent.
- Do not modify Git history, GitHub remote configuration, or the newly added `LICENSE`.
- Use `Buildable` for visible title-cased product copy, `buildable` for CLI/files/package names, and `BUILDABLE_` for environment variables.
- Keep API endpoint paths unchanged; this is a product identity rename, not an API version change.
- Verify both the full test/check suite and browser acceptance after the rename.

---

### Task 1: Rename Backend Runtime And Persistence Identifiers

**Files:**
- Modify: `backend/pyproject.toml`, `backend/uv.lock`, `backend/alembic.ini`
- Modify: `backend/app/config.py`, `backend/app/main.py`, `backend/app/cli.py`, `backend/app/services/auth.py`, `backend/app/services/backup.py`, `backend/app/schemas/backup.py`, `backend/app/api/backups.py`
- Rename: the backend package to `backend/src/buildable_api/`
- Modify/Test: affected `backend/tests/**`

**Interfaces:**
- Consumes: `BUILDABLE_*` environment variables and `buildable` console command.
- Produces: `buildable.backup/v1`, `buildable_session`, `buildable.db`, and `buildable-backup-*.json` export names.

- [ ] **Step 1: Write failing backend identity tests**

```python
def test_runtime_uses_buildable_identifiers(client):
    assert client.app.title == "Buildable"
    assert "buildable_session=" in client.post("/api/auth/login", json={"password": "secret"}).headers["set-cookie"]

def test_backup_uses_buildable_wire_and_filename(client):
    response = client.get("/api/backups/export")
    assert response.json()["schema"] == "buildable.backup/v1"
    assert 'filename="buildable-backup-' in response.headers["content-disposition"]
```

- [ ] **Step 2: Run focused tests and verify the existing identity fails**

Run: `cd backend && uv run pytest tests/api/test_auth.py tests/api/test_settings.py -v`

Expected: assertions expecting Buildable identifiers fail before implementation.

- [ ] **Step 3: Rename backend settings, CLI, backup, cookie, package, and database identifiers**

```toml
[project]
name = "buildable-api"

[project.scripts]
buildable = "app.cli:main"
```

```python
class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/buildable.db"
    model_config = SettingsConfigDict(env_prefix="BUILDABLE_", env_file=".env")
```

Use `Buildable` in FastAPI metadata, `buildable_session` for the cookie, and `buildable.backup/v1`/`buildable-backup-*.json` for backup formats and export headers. Update every affected test literal, generated file path, and package directory consistently.

- [ ] **Step 4: Run focused backend tests and CLI smoke test**

Run: `cd backend && uv run pytest tests/api/test_auth.py tests/api/test_settings.py tests/services/test_backup.py -v && uv run buildable --help`

Expected: all focused tests and the renamed CLI pass; the old command is no longer documented.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "refactor: rename backend runtime to buildable"
```

### Task 2: Rename Frontend, Deployment, And Operational Surfaces

**Files:**
- Modify: `frontend/src/**`, `frontend/e2e/**`, `frontend/playwright.config.ts`
- Modify: `Dockerfile`, `compose.yaml`, `.env.example`, `scripts/reset-password.sh`, `README.md`, `frontend/README.md`
- Modify/Test: affected `frontend/**/*.test.ts`

**Interfaces:**
- Consumes: backend `BUILDABLE_*` variables and `buildable` CLI.
- Produces: visible `Buildable` branding, deployment settings with `BUILDABLE_*`, and browser fixtures rooted at `buildable-*` temporary paths.

- [ ] **Step 1: Write failing frontend/deployment identity tests**

```typescript
it('brands the unlock page as Buildable', () => {
  render(UnlockPage);
  expect(screen.getByRole('link', { name: 'Buildable' })).toBeInTheDocument();
});
```

```python
def test_production_configuration_uses_buildable_env_names():
    assert "BUILDABLE_FRONTEND_DIR" in Path("../../Dockerfile").read_text()
    assert "BUILDABLE_" in Path("../../Dockerfile").read_text()
```

- [ ] **Step 2: Run focused tests and verify old branding fails**

Run: `cd frontend && npm test -- UnlockPage.test.ts`

Expected: Buildable branding assertion fails before implementation.

- [ ] **Step 3: Rename visible copy, frontend titles, deployment variables, scripts, and examples**

```yaml
environment:
  BUILDABLE_DATABASE_URL: sqlite:////data/buildable.db
  BUILDABLE_SESSION_SECRET: ${BUILDABLE_SESSION_SECRET:?set BUILDABLE_SESSION_SECRET in .env}
```

Replace all UI wordmarks/titles, Playwright database paths and server command variables, Docker environment names, Compose values, reset script command, and README examples with the new identity.

- [ ] **Step 4: Run frontend and production-focused verification**

Run: `cd frontend && npm test && npm run check && npm run build && npx playwright test --project=chromium --project=mobile`

Expected: all frontend/unit/browser checks pass under the Buildable runtime names.

- [ ] **Step 5: Commit**

```bash
git add frontend Dockerfile compose.yaml .env.example scripts README.md
git commit -m "refactor: rebrand application and deployment as buildable"
```

### Task 3: Remove Remaining Tracked Legacy References And Verify

**Files:**
- Modify: `docs/superpowers/plans/2026-08-10-lego-inventory-v1.md`
- Modify: any tracked file reported by the legacy-identity scan.
- Test: backend/frontend full suites

**Interfaces:**
- Consumes: completed backend/frontend rename.
- Produces: no tracked product/runtime references to the legacy identity.

- [ ] **Step 1: Add the scan as a failing verification gate**

```bash
if git grep -in -e '[w]hat2build'; then
  echo 'legacy identity remains'
  exit 1
fi
```

- [ ] **Step 2: Run the scan and inspect every remaining tracked hit**

Run: `git grep -in -e '[w]hat2build'`

Expected: hits identify historical plan text, fixture literals, and any missed deployment/runtime identifier.

- [ ] **Step 3: Rename remaining tracked content deliberately**

Update plan/documentation examples, fixture names, test literals, and any tracked paths so the case-insensitive scan returns no results. Do not rename Git metadata or generated virtual environments.

- [ ] **Step 4: Run final repository verification**

Run: `make test && make check && cd frontend && npx playwright test --project=chromium --project=mobile && cd .. && git grep -in -e '[w]hat2build' && git diff --check`

Expected: test/check/browser commands pass; the legacy scan emits no matches; diff check is clean.

- [ ] **Step 5: Commit**

```bash
git add docs backend frontend Dockerfile compose.yaml .env.example README.md scripts
git commit -m "docs: complete buildable rebrand"
```
