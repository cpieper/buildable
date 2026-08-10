import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CorrectionEditor from './CorrectionEditor.svelte';

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const set = { set_num: '1234-1', name: 'Original', year: 1999, theme_name: 'Space', num_parts: 2, image_url: null, external_url: null, instructions_url: null, has_local_overrides: true, parts: [{ part_num: '3001', part_name: 'Brick', color_id: 5, color_name: 'Red', rgb_hex: 'C91A09', quantity: 2, is_spare: false, source_kind: 'set', image_url: null }] };
const metadata = { imported: { name: 'Original', year: 1999, theme_name: 'Space', num_parts: 2 }, override: { name: 'Corrected', year: null, theme_name: null, num_parts: null, reason: 'Catalog correction' }, effective: { name: 'Corrected', year: 1999, theme_name: 'Space', num_parts: 2 }, has_local_overrides: true };
const part = { imported: set.parts[0], override: { part_num: '3001', color_id: 5, is_spare: false, operation: 'upsert', quantity: 4, reason: 'Counted' }, effective: { ...set.parts[0], quantity: 4 }, has_local_overrides: true };

describe('CorrectionEditor', () => {
	beforeEach(() => vi.restoreAllMocks());

	it('reloads saved metadata and part overrides from the wrapper response', async () => {
		vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
			const url = String(input);
			if (url === '/api/catalog/sets/1234-1') return json(set);
			if (url === '/api/overrides/sets/1234-1') return json({ metadata, parts: [part] });
			return json({}, 500);
		});
		render(CorrectionEditor);
		await fireEvent.input(screen.getByLabelText('Set number'), { target: { value: '1234-1' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Load set' }));
		expect(await screen.findByText('Local: Corrected')).toBeInTheDocument();
		expect(screen.getByText(/Imported quantity 2/)).toBeInTheDocument();
		expect(screen.getByText(/Effective quantity 4/)).toBeInTheDocument();
	});

	it('saves then removes a part correction and reloads effective values', async () => {
		let saved: typeof part | null = null;
		vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
			const url = String(input); const method = init?.method ?? 'GET';
			if (url === '/api/catalog/sets/1234-1') return json(set);
			if (url === '/api/overrides/sets/1234-1' && method === 'GET') return saved ? json({ metadata, parts: [saved] }) : json({ detail: 'No local overrides for set' }, 404);
			if (url === '/api/overrides/sets/1234-1/parts/3001/5' && method === 'PUT') { saved = part; return json(part); }
			if (url === '/api/overrides/sets/1234-1/parts/3001/5' && method === 'DELETE') { saved = null; return new Response(null, { status: 204 }); }
			return json({}, 500);
		});
		render(CorrectionEditor);
		await fireEvent.input(screen.getByLabelText('Set number'), { target: { value: '1234-1' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Load set' }));
		await fireEvent.click(await screen.findByRole('button', { name: 'Correct part' }));
		await fireEvent.input(screen.getByLabelText('Effective quantity'), { target: { value: '4' } });
		await fireEvent.input(screen.getAllByLabelText('Correction reason').at(-1)!, { target: { value: 'Counted pieces' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save part correction' }));
		expect(await screen.findByText(/Effective quantity 4/)).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'Correct part' }));
		await fireEvent.input(screen.getAllByLabelText('Correction reason').at(-1)!, { target: { value: 'Undo count' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Remove local correction' }));
		expect(await screen.findByText(/Effective quantity 2/)).toBeInTheDocument();
	});

	it('reclassifies a part as spare without leaving the imported identity effective', async () => {
		const calls: Array<{ body: { operation: string; is_spare: boolean; quantity: number | null } }> = [];
		const reclassified = { ...part, imported: null, override: { ...part.override, is_spare: true, quantity: 2 }, effective: { ...set.parts[0], is_spare: true, quantity: 2 } };
		vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
			const url = String(input); const method = init?.method ?? 'GET';
			if (url === '/api/catalog/sets/1234-1') return json(set);
			if (url === '/api/overrides/sets/1234-1' && method === 'GET') return calls.length === 2 ? json({ metadata, parts: [{ ...part, override: { ...part.override, operation: 'delete', quantity: null }, effective: null }, reclassified] }) : json({ detail: 'No local overrides for set' }, 404);
			if (url === '/api/overrides/sets/1234-1/parts/3001/5' && method === 'PUT') { calls.push({ body: JSON.parse(String(init?.body)) }); return json({}); }
			return json({}, 500);
		});
		render(CorrectionEditor);
		await fireEvent.input(screen.getByLabelText('Set number'), { target: { value: '1234-1' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Load set' }));
		await fireEvent.click(await screen.findByRole('button', { name: 'Correct part' }));
		await fireEvent.click(screen.getByLabelText('Spare part'));
		await fireEvent.input(screen.getAllByLabelText('Correction reason').at(-1)!, { target: { value: 'This is a spare' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save part correction' }));
		expect(await screen.findByText(/Local delete/)).toBeInTheDocument();
		expect(screen.getByText(/Effective quantity 0/)).toBeInTheDocument();
		expect(calls.map((call) => ({ operation: call.body.operation, is_spare: call.body.is_spare, quantity: call.body.quantity }))).toEqual([{ operation: 'delete', is_spare: false, quantity: null }, { operation: 'upsert', is_spare: true, quantity: 2 }]);
	});

	it('labels a target-only local upsert without inventing an imported quantity', async () => {
		const target = { ...set.parts[0], is_spare: true, quantity: 2, source_kind: 'override' };
		const targetOverride = { imported: null, override: { ...part.override, is_spare: true, quantity: 2 }, effective: target, has_local_overrides: true };
		vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
			if (String(input) === '/api/catalog/sets/1234-1') return json({ ...set, parts: [] });
			return json({ metadata, parts: [targetOverride] });
		});
		render(CorrectionEditor);
		await fireEvent.input(screen.getByLabelText('Set number'), { target: { value: '1234-1' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Load set' }));
		expect(await screen.findByText('Imported none · Local 2 · Effective quantity 2')).toBeInTheDocument();
		expect(screen.queryByText(/Imported quantity 2/)).not.toBeInTheDocument();
	});

	it('shows imported, local, and effective metadata values independently', async () => {
		vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => String(input) === '/api/catalog/sets/1234-1' ? json(set) : json({ metadata, parts: [] }));
		render(CorrectionEditor);
		await fireEvent.input(screen.getByLabelText('Set number'), { target: { value: '1234-1' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Load set' }));
		expect(await screen.findByText('Local: Corrected')).toBeInTheDocument();
		expect(screen.getAllByText('Local: inherited').length).toBe(3);
		expect(screen.getByText('Effective: 1999')).toBeInTheDocument();
		expect(screen.getByText('Imported: 2')).toBeInTheDocument();
	});

	it('removes both identities from a target-only reclassified catalog row', async () => {
		const targetSet = { ...set, parts: [{ ...set.parts[0], is_spare: true, quantity: 2, source_kind: 'override' }] };
		const targetOverride = { imported: null, override: { ...part.override, is_spare: true, quantity: 2 }, effective: targetSet.parts[0], has_local_overrides: true };
		const originalDelete = { imported: set.parts[0], override: { ...part.override, operation: 'delete', quantity: null, is_spare: false }, effective: null, has_local_overrides: true };
		const deleteCalls: Array<{ is_spare: boolean; reason: string }> = []; let removed = false;
		vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
			const url = String(input); const method = init?.method ?? 'GET';
			if (url === '/api/catalog/sets/1234-1') return json(removed ? set : targetSet);
			if (url === '/api/overrides/sets/1234-1' && method === 'GET') return removed ? json({ detail: 'No local overrides for set' }, 404) : json({ metadata, parts: [targetOverride, originalDelete] });
			if (url === '/api/overrides/sets/1234-1/parts/3001/5' && method === 'DELETE') { deleteCalls.push(JSON.parse(String(init?.body))); if (deleteCalls.length === 2) removed = true; return new Response(null, { status: 204 }); }
			return json({}, 500);
		});
		render(CorrectionEditor);
		await fireEvent.input(screen.getByLabelText('Set number'), { target: { value: '1234-1' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Load set' }));
		await fireEvent.click((await screen.findAllByRole('button', { name: 'Correct part' }))[0]);
		await fireEvent.input(screen.getAllByLabelText('Correction reason').at(-1)!, { target: { value: 'Restore source row' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Remove local correction' }));
		expect(await screen.findByText(/Imported quantity 2 · Local none · Effective quantity 2/)).toBeInTheDocument();
		expect(deleteCalls).toEqual([{ is_spare: true, reason: 'Restore source row' }, { is_spare: false, reason: 'Restore source row' }]);
	});

	it('shows and restores a standalone delete missing from effective catalog results', async () => {
		const deleted = { imported: set.parts[0], override: { ...part.override, operation: 'delete', quantity: null }, effective: null, has_local_overrides: true };
		let restored = false;
		vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
			const url = String(input); const method = init?.method ?? 'GET';
			if (url === '/api/catalog/sets/1234-1') return json(restored ? set : { ...set, parts: [] });
			if (url === '/api/overrides/sets/1234-1' && method === 'GET') return restored ? json({ detail: 'No local overrides for set' }, 404) : json({ metadata, parts: [deleted] });
			if (url === '/api/overrides/sets/1234-1/parts/3001/5' && method === 'DELETE') { restored = true; return new Response(null, { status: 204 }); }
			return json({}, 500);
		});
		render(CorrectionEditor);
		await fireEvent.input(screen.getByLabelText('Set number'), { target: { value: '1234-1' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Load set' }));
		expect(await screen.findByText(/Imported quantity 2 · Local delete · Effective quantity 0/)).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'Correct part' }));
		await fireEvent.input(screen.getAllByLabelText('Correction reason').at(-1)!, { target: { value: 'Restore row' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Remove local correction' }));
		expect(await screen.findByText(/Imported quantity 2 · Local none · Effective quantity 2/)).toBeInTheDocument();
	});

	it('saves only metadata fields intentionally changed from their effective values', async () => {
		let payload: Record<string, unknown> | null = null;
		vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
			const url = String(input); const method = init?.method ?? 'GET';
			if (url === '/api/catalog/sets/1234-1') return json(set);
			if (url === '/api/overrides/sets/1234-1' && method === 'GET') return json({ metadata, parts: [] });
			if (url === '/api/overrides/sets/1234-1' && method === 'PUT') { payload = JSON.parse(String(init?.body)); return json(metadata); }
			return json({}, 500);
		});
		render(CorrectionEditor);
		await fireEvent.input(screen.getByLabelText('Set number'), { target: { value: '1234-1' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Load set' }));
		await fireEvent.input(await screen.findByLabelText('Name'), { target: { value: 'New title' } });
		await fireEvent.input(screen.getByLabelText('Correction reason'), { target: { value: 'Correct title' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save correction' }));
		expect(payload).toEqual({ name: 'New title', reason: 'Correct title' });
	});
});
