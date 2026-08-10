import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CollectionPage from './+page.svelte';

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const owned = { id: 1, set_num: '10497-1', set_name: 'Galaxy Explorer', quantity: 1, completeness: 'complete', unknown_missing_count: 0, unknown_missing_note: null, notes: null, known_missing_total: 0, has_local_overrides: false, added_at: '2026-08-10T00:00:00Z', updated_at: '2026-08-10T00:00:00Z' };

describe('collection page', () => {
	beforeEach(() => {
		let added = false; let missing = [] as unknown[];
		vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
			const url = String(input); const method = init?.method ?? 'GET';
			if (url.startsWith('/api/collection') && method === 'GET' && !url.includes('missing-parts')) return json(added ? [owned] : []);
			if (url.startsWith('/api/catalog/sets?q=')) return json([{ set_num: '10497-1', name: 'Galaxy Explorer', year: 2022, theme_name: 'Space', num_parts: 1254, image_url: null, has_local_overrides: false }]);
			if (url === '/api/collection' && method === 'POST') { added = true; return json(owned, 201); }
			if (url === '/api/catalog/sets/10497-1') return json({ ...owned, year: 2022, theme_name: 'Space', num_parts: 1254, image_url: null, external_url: null, instructions_url: null, parts: [{ part_num: '3023', part_name: 'Plate 1 x 2, Red', color_id: 4, color_name: 'Red', rgb_hex: 'C91A09', quantity: 4, is_spare: false, source_kind: 'set', image_url: null }] });
			if (url === '/api/collection/1/missing-parts' && method === 'GET') return json(missing);
			if (url === '/api/collection/1/missing-parts' && method === 'POST') { missing = [{ id: 4, owned_set_id: 1, part_num: '3023', color_id: 4, quantity: 2, note: null }]; return json(missing[0], 201); }
			return json({ detail: `Unhandled ${method} ${url}` }, 500);
		});
	});

	it('adds a cached set and records a known missing piece', async () => {
		render(CollectionPage);
		await fireEvent.click(await screen.findByRole('button', { name: 'Add set' }));
		await fireEvent.input(screen.getByLabelText('Set number or name'), { target: { value: 'Galaxy Explorer' } });
		await new Promise((resolve) => setTimeout(resolve, 300));
		await fireEvent.click(await screen.findByRole('option', { name: /10497-1 Galaxy Explorer/ }));
		await fireEvent.click(screen.getByRole('button', { name: 'Add to collection' }));
		await fireEvent.click(await screen.findByRole('button', { name: 'Edit missing pieces' }));
		await fireEvent.click(await screen.findByRole('button', { name: /Plate 1 x 2, Red/ }));
		await fireEvent.input(screen.getByLabelText('Missing quantity'), { target: { value: '2' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save missing piece' }));
		expect(await screen.findByText('2 known missing')).toBeInTheDocument();
	});

	it('collects add details and imports a selected remote result before saving it', async () => {
		let remoteImported = false;
		vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
			const url = String(input); const method = init?.method ?? 'GET';
			if (url === '/api/collection') return json([]);
			if (url === '/api/settings/status') return json({ api_key_configured: true });
			if (url.startsWith('/api/catalog/sets?')) return json([]);
			if (url.startsWith('/api/catalog/remote-search?')) return json([{ set_num: '99999-1', name: 'Remote Explorer', year: 2026, theme_id: 1, num_parts: 10, image_url: 'https://example.com/set.png', external_url: null }]);
			if (url === '/api/catalog/lookup/99999-1' && method === 'POST') { remoteImported = true; return json({ set: {}, summary: {} }); }
			if (url === '/api/collection' && method === 'POST') return json(owned, 201);
			return json({}, 200);
		});
		render(CollectionPage);
		await fireEvent.click(await screen.findByRole('button', { name: 'Add set' }));
		await fireEvent.input(screen.getByLabelText('Set number or name'), { target: { value: 'Remote Explorer' } });
		await new Promise((resolve) => setTimeout(resolve, 300));
		await fireEvent.click(await screen.findByRole('option', { name: /99999-1 Remote Explorer/ }));
		await fireEvent.input(screen.getByLabelText('Quantity'), { target: { value: '2' } });
		await fireEvent.input(screen.getByLabelText('Notes'), { target: { value: 'shelf A' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Add to collection' }));
		expect(remoteImported).toBe(true);
	});
});
