import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SettingsPage from './+page.svelte';

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const validBackup = { schema: 'buildable.backup/v1', exported_at: '2026-08-10T00:00:00Z', owned_sets: [{ set_num: '10497-1', quantity: 1, completeness: 'complete', unknown_missing_count: 0 }, { set_num: '31109-1', quantity: 1, completeness: 'complete', unknown_missing_count: 0 }], missing_parts: [], set_overrides: [], set_part_overrides: [], equivalence_groups: [{ name: 'Existing group', part_nums: ['3001', '3002'] }], settings: {} };

describe('settings page', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
		let groups: unknown[] = [];
		vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
			const url = String(input); const method = init?.method ?? 'GET';
			if (url === '/api/settings/status') return json({ api_key_configured: true, last_successful_import: null, latest_failed_import: null, catalog_counts: { sets: 3, parts: 4, colors: 2 }, database_label: 'buildable.db', backup_schema: 'buildable.backup/v1' });
			if (url === '/api/equivalence-groups' && method === 'GET') return json(groups);
			if (url === '/api/backups/validate' && method === 'POST') return json({ valid: true, missing_dependencies: {} });
			if (url === '/api/equivalence-groups' && method === 'POST') { const group = { id: 4, name: 'Jumper variants', part_nums: ['15573', '3794b'], notes: null, created_at: '2026-08-10T00:00:00Z', updated_at: '2026-08-10T00:00:00Z' }; groups = [group]; return json(group, 201); }
			return json({ detail: `Unhandled ${method} ${url}` }, 500);
		});
	});

	it('validates a restore before enabling replace', async () => {
		render(SettingsPage);
		const file = new File([JSON.stringify(validBackup)], 'buildable-backup.json', { type: 'application/json' });
		await fireEvent.change(await screen.findByLabelText('Backup file'), { target: { files: [file] } });
		expect(await screen.findByText('2 owned sets, 1 equivalence group')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('radio', { name: 'Replace local data' }));
		expect(screen.getByRole('button', { name: 'Replace local data' })).toBeDisabled();
		await fireEvent.input(screen.getByLabelText('Type REPLACE to confirm'), { target: { value: 'REPLACE' } });
		expect(screen.getByRole('button', { name: 'Replace local data' })).toBeEnabled();
	});

	it('creates an explicit equivalence group with two members', async () => {
		render(SettingsPage);
		await fireEvent.click(await screen.findByRole('button', { name: 'New equivalence group' }));
		await fireEvent.input(screen.getByLabelText('Group name'), { target: { value: 'Jumper variants' } });
		await fireEvent.input(screen.getByLabelText('Search part number'), { target: { value: '15573' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Add part' }));
		await fireEvent.input(screen.getByLabelText('Search part number'), { target: { value: '3794b' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Add part' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Save group' }));
		expect(await screen.findByText('Jumper variants')).toBeInTheDocument();
	});

	it('describes catalog imports as buildable candidate data instead of owned collection import', async () => {
		render(SettingsPage);
		expect(await screen.findByText(/Import set references and inventories/)).toBeInTheDocument();
		expect(screen.getByText(/This does not add sets to your collection/)).toBeInTheDocument();
	});

	it('imports a discovery CSV as catalog candidates instead of owned collection rows', async () => {
		const calls: Array<[string, RequestInit | undefined]> = [];
		vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
			const url = String(input); const method = init?.method ?? 'GET';
			calls.push([url, init]);
			if (url === '/api/settings/status') return json({ api_key_configured: true, last_successful_import: null, latest_failed_import: null, catalog_counts: { sets: 3, parts: 4, colors: 2 }, database_label: 'buildable.db', backup_schema: 'buildable.backup/v1' });
			if (url === '/api/equivalence-groups') return json([]);
			if (url === '/api/catalog/discovery-import' && method === 'POST') return json({ sets_imported: 2, rows_skipped: 0, skipped_set_nums: [], warnings: [], started_at: '2026-08-12T00:00:00Z', completed_at: '2026-08-12T00:00:01Z' });
			return json({ detail: `Unhandled ${method} ${url}` }, 500);
		});

		render(SettingsPage);
		const file = new File(['Set Number\n10497-1\n31109-1\n'], 'discovery.csv', { type: 'text/csv' });
		await fireEvent.change(await screen.findByLabelText('Discovery CSV'), { target: { files: [file] } });

		expect(await screen.findByText('Imported 2 discovery sets for matching.')).toBeInTheDocument();
		expect(calls.some(([url, init]) => url === '/api/catalog/discovery-import' && init?.method === 'POST')).toBe(true);
	});

	it('shows structured missing backup dependencies from a 422 validation response', async () => {
		vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
			const url = String(input); const method = init?.method ?? 'GET';
			if (url === '/api/settings/status') return json({ api_key_configured: false, last_successful_import: null, latest_failed_import: null, catalog_counts: { sets: 0, parts: 0, colors: 0 }, database_label: 'buildable.db', backup_schema: 'buildable.backup/v1' });
			if (url === '/api/equivalence-groups') return json([]);
			if (url === '/api/backups/validate' && method === 'POST') return json({ detail: { code: 'missing_catalog_dependencies', message: 'Import catalog records first', missing_dependencies: { sets: ['10497-1'], parts: ['3001'] } } }, 422);
			return json({}, 500);
		});
		render(SettingsPage);
		const file = new File([JSON.stringify(validBackup)], 'buildable-backup.json', { type: 'application/json' });
		await fireEvent.change(await screen.findByLabelText('Backup file'), { target: { files: [file] } });
		expect(await screen.findByText(/sets: 10497-1, parts: 3001/)).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Merge local data' })).not.toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Import the catalog first.' })).toHaveAttribute('href', '#catalog-import');
	});
});
