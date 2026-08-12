# Buildable Candidate Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Include owned sets in Buildable Sets by default and guide users toward populating the local candidate catalog.

**Architecture:** Reuse the existing recommendations API `hide_owned` parameter. Add UI state and copy in Svelte, with tests exercising request URLs and visible user guidance.

**Tech Stack:** FastAPI, SQLAlchemy, Svelte 5, Vitest, Testing Library.

## Global Constraints

- Candidate expansion stays local-first: ZIP import for broad catalog coverage, Rebrickable lookup for targeted set import, and manual catalog entry for one-off records.
- The Buildable Sets default sends `hide_owned=false`.
- The user can turn off owned sets with a top-level "Include owned sets" toggle.
- Catalog import wording must not read as importing the user's owned collection.
- Empty Buildable Sets guidance must show concrete next actions.

---

### Task 1: Buildable Owned-Set Toggle And Empty Guidance

**Files:**
- Modify: `frontend/src/routes/buildable/+page.svelte`
- Test: `frontend/src/routes/buildable/buildable.test.ts`

**Interfaces:**
- Consumes: existing `/api/recommendations` query parameter `hide_owned`.
- Produces: frontend URL parameter `include_owned=0` only when owned sets are excluded.

- [ ] **Step 1: Write failing tests**

Add tests that inspect fetched `/api/recommendations` URLs and visible empty-state text:

```typescript
it('includes owned sets by default and can exclude them with a top-level toggle', async () => {
  const recommendationUrls: string[] = [];
  vi.mocked(globalThis.fetch).mockImplementation(async (input) => {
    const url = String(input);
    if (url.startsWith('/api/recommendations')) {
      recommendationUrls.push(url);
      return json({ items: [], total_candidates: 0, offset: 0, limit: 50, max_pieces: 1000, theme: null, year_from: null, year_to: null, hide_owned: false, status: null, sort: 'buildability', direction: 'asc' });
    }
    if (url === '/api/settings/status') return json({ api_key_configured: false });
    return json([]);
  });

  render(BuildablePage);
  expect(await screen.findByRole('checkbox', { name: 'Include owned sets' })).toBeChecked();
  expect(new URL(recommendationUrls.at(-1)!, 'http://localhost').searchParams.get('hide_owned')).toBe('false');
  await fireEvent.click(screen.getByRole('checkbox', { name: 'Include owned sets' }));
  await vi.waitFor(() => expect(new URL(recommendationUrls.at(-1)!, 'http://localhost').searchParams.get('hide_owned')).toBe('true'));
  expect(window.location.search).toContain('include_owned=0');
});

it('shows candidate-pool guidance when no buildable sets match', async () => {
  render(BuildablePage);
  expect(await screen.findByText('No sets match this view yet.')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Import a Rebrickable catalog ZIP' })).toHaveAttribute('href', '/settings#catalog-import');
  expect(screen.getByText(/Catalog imports add set references and inventories for matching/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Verify the tests fail**

Run: `cd frontend && npm test -- src/routes/buildable/buildable.test.ts --run`

Expected: FAIL because the checkbox and empty-state guidance do not exist and requests do not send `hide_owned=false`.

- [ ] **Step 3: Implement minimal Svelte changes**

Add `includeOwned` state restored from `include_owned`, include `hide_owned` in the recommendations query, show a top-level checkbox above filters, and replace the no-results empty paragraph with guidance links.

- [ ] **Step 4: Verify buildable tests pass**

Run: `cd frontend && npm test -- src/routes/buildable/buildable.test.ts --run`

Expected: PASS.

### Task 2: Catalog Import Language

**Files:**
- Modify: `frontend/src/lib/components/settings/CatalogImportPanel.svelte`
- Test: `frontend/src/routes/settings/settings.test.ts`

**Interfaces:**
- Consumes: existing Settings page rendering of `CatalogImportPanel`.
- Produces: clearer user copy only; no API changes.

- [ ] **Step 1: Write failing test**

Add a Settings page test that proves the catalog panel copy distinguishes matching candidates from collection ownership:

```typescript
it('describes catalog imports as buildable candidate data instead of owned collection import', async () => {
  render(SettingsPage);
  expect(await screen.findByText(/Import set references and inventories/)).toBeInTheDocument();
  expect(screen.getByText(/This does not add sets to your collection/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Verify the test fails**

Run: `cd frontend && npm test -- src/routes/settings/settings.test.ts --run`

Expected: FAIL because the copy is not present.

- [ ] **Step 3: Update the panel copy**

Change the panel title/description/button support text so it says catalog imports add buildable candidate data, while collection import remains separate.

- [ ] **Step 4: Verify settings tests pass**

Run: `cd frontend && npm test -- src/routes/settings/settings.test.ts --run`

Expected: PASS.

### Task 3: Regression Sweep

**Files:**
- Test only.

**Interfaces:**
- Consumes: completed UI changes from Tasks 1 and 2.
- Produces: verified frontend behavior.

- [ ] **Step 1: Run focused frontend tests**

Run: `cd frontend && npm test -- src/routes/buildable/buildable.test.ts src/routes/settings/settings.test.ts --run`

Expected: PASS.

- [ ] **Step 2: Run backend recommendation tests**

Run: `cd backend && uv run pytest tests/api/test_recommendations.py`

Expected: PASS, confirming the existing `hide_owned` API contract still behaves.
