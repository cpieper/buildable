import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import BuildablePage from './+page.svelte';

const navigation = vi.hoisted(() => ({ goto: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto: navigation.goto }));

const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
const exact = { set_num: '10497-1', name: 'Galaxy Explorer', year: 2022, theme_name: 'Space', num_parts: 1254, image_url: null, has_local_overrides: false, status: 'exact', counts: { required: 100, exact: 100, color_substitution: 0, equivalence_substitution: 0, missing: 0 }, percent_exact: 100, percent_buildable: 100 };
const swaps = { set_num: '31109-1', name: 'Pirate Ship', year: 2020, theme_name: 'Creator', num_parts: 1264, image_url: null, has_local_overrides: false, status: 'substitution', counts: { required: 100, exact: 94, color_substitution: 6, equivalence_substitution: 0, missing: 0 }, percent_exact: 94, percent_buildable: 100 };
const missing = { set_num: '40501-1', name: 'Missing Set', year: 2021, theme_name: 'Ideas', num_parts: 30, image_url: null, has_local_overrides: false, status: 'missing', counts: { required: 10, exact: 7, color_substitution: 0, equivalence_substitution: 0, missing: 3 }, percent_exact: 70, percent_buildable: 70 };

	describe('buildable page', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
		navigation.goto.mockReset();
		window.history.replaceState({}, '', '/buildable');
		vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
			const url = String(input);
			if (url.startsWith('/api/recommendations')) {
				const missingEnabled = new URL(url, 'http://localhost').searchParams.get('status')?.includes('missing');
				return json({ items: missingEnabled ? [exact, swaps, missing] : [exact, swaps], total_candidates: missingEnabled ? 3 : 2, offset: 0, limit: 50, max_pieces: 1000, theme: null, year_from: null, year_to: null, hide_owned: true, status: null, sort: 'buildability', direction: 'asc' });
			}
			if (url === '/api/settings/status') return json({ api_key_configured: false });
			return json([]);
		});
	});

	it('restores a shared status query and preserves zero selected statuses as zero results', async () => {
		window.history.replaceState({}, '', '/buildable?status=exact%2Csubstitution%2Cmissing');
		render(BuildablePage);
		expect((await screen.findByRole('checkbox', { name: 'Exact builds' }) as HTMLInputElement).checked).toBe(true);
		expect((screen.getByRole('checkbox', { name: 'Color swaps' }) as HTMLInputElement).checked).toBe(true);
		expect((screen.getByRole('checkbox', { name: 'Missing pieces' }) as HTMLInputElement).checked).toBe(true);
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Exact builds' }));
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Color swaps' }));
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Missing pieces' }));
		expect(await screen.findByText('No match statuses are selected.')).toBeInTheDocument();
		expect(window.location.search).toContain('status=none');
	});

	it('keeps the newer recommendation response when an aborted request resolves late', async () => {
		let resolveFirst!: (response: Response) => void;
		let calls = 0;
		const first = new Promise<Response>((resolve) => { resolveFirst = resolve; });
		vi.mocked(globalThis.fetch).mockImplementation((input) => {
			const url = String(input);
			if (url.startsWith('/api/recommendations')) return ++calls === 1 ? first : Promise.resolve(json({ items: [exact], total_candidates: 1, offset: 0, limit: 50, max_pieces: 1000, theme: null, year_from: null, year_to: null, hide_owned: true, status: ['exact'], sort: 'buildability', direction: 'asc' }));
			if (url === '/api/settings/status') return Promise.resolve(json({ api_key_configured: false }));
			return Promise.resolve(json([]));
		});
		render(BuildablePage);
		await fireEvent.click(await screen.findByRole('checkbox', { name: 'Missing pieces' }));
		await Promise.resolve();
		expect(await screen.findByText('Galaxy Explorer')).toBeInTheDocument();
		resolveFirst(json({ items: [missing], total_candidates: 1, offset: 0, limit: 50, max_pieces: 1000, theme: null, year_from: null, year_to: null, hide_owned: true, status: ['missing'], sort: 'buildability', direction: 'asc' }));
		await new Promise((resolve) => setTimeout(resolve, 0));
		expect(screen.queryByText('Missing Set')).not.toBeInTheDocument();
	});

	it('includes owned sets by default and can exclude them with a top-level toggle', async () => {
		const recommendationUrls: string[] = [];
		vi.mocked(globalThis.fetch).mockImplementation(async (input) => {
			const url = String(input);
			if (url.startsWith('/api/recommendations')) {
				recommendationUrls.push(url);
				const hideOwned = new URL(url, 'http://localhost').searchParams.get('hide_owned') === 'true';
				return json({ items: hideOwned ? [swaps] : [exact, swaps], total_candidates: hideOwned ? 1 : 2, offset: 0, limit: 50, max_pieces: 1000, theme: null, year_from: null, year_to: null, hide_owned: hideOwned, status: null, sort: 'buildability', direction: 'asc' });
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
		expect(screen.queryByText('Galaxy Explorer')).not.toBeInTheDocument();
	});

	it('shows candidate-pool guidance when no buildable sets match', async () => {
		vi.mocked(globalThis.fetch).mockImplementation(async (input) => {
			const url = String(input);
			if (url.startsWith('/api/recommendations')) return json({ items: [], total_candidates: 0, offset: 0, limit: 50, max_pieces: 1000, theme: null, year_from: null, year_to: null, hide_owned: false, status: null, sort: 'buildability', direction: 'asc' });
			if (url === '/api/settings/status') return json({ api_key_configured: false });
			return json([]);
		});

		render(BuildablePage);
		expect(await screen.findByText('No sets match this view yet.')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Import a Rebrickable catalog ZIP' })).toHaveAttribute('href', '/settings#catalog-import');
		expect(screen.getByText(/Catalog imports add set references and inventories for matching/)).toBeInTheDocument();
		expect(screen.getByText(/Start with exact builds and color swaps/)).toBeInTheDocument();
		expect(screen.getByText(/Near misses are useful when a tiny parts order would unlock a set/)).toBeInTheDocument();
	});

	it('retries a failed remote import and only opens detail after the import succeeds', async () => {
		let importAttempt = 0;
		vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
			const url = String(input); const method = init?.method ?? 'GET';
			if (url === '/api/settings/status') return json({ api_key_configured: true });
			if (url.startsWith('/api/recommendations')) return json({ items: [], total_candidates: 0, offset: 0, limit: 50, max_pieces: 1000, theme: null, year_from: null, year_to: null, hide_owned: true, status: null, sort: 'buildability', direction: 'asc' });
			if (url.startsWith('/api/catalog/sets?')) return json([]);
			if (url.startsWith('/api/catalog/remote-search?')) return json([{ set_num: '99999-1', name: 'Remote Explorer', year: 2026, theme_id: 1, num_parts: 10, image_url: null, external_url: null }]);
			if (url === '/api/catalog/lookup/99999-1' && method === 'POST') return ++importAttempt === 1 ? new Response(JSON.stringify({ detail: 'Network unavailable' }), { status: 503, headers: { 'Content-Type': 'application/json' } }) : json({ set: {}, summary: {} });
			return json([]);
		});
		render(BuildablePage);
		await new Promise((resolve) => setTimeout(resolve, 0));
		await fireEvent.input(screen.getByLabelText('Search a build target'), { target: { value: 'Remote Explorer' } });
		await new Promise((resolve) => setTimeout(resolve, 260));
		await fireEvent.click(await screen.findByRole('option', { name: /Remote Explorer/ }));
		expect(await screen.findByText('Couldn’t import Remote Explorer.')).toBeInTheDocument();
		expect(navigation.goto).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: 'Retry import' }));
		await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalledWith('/sets/99999-1'));
	});

	it('shows exact sets before color-substitution sets and can reveal missing sets', async () => {
		render(BuildablePage);
		const rows = await screen.findAllByRole('article');
		expect(within(rows[0]).getByText('Exact build')).toBeInTheDocument();
		expect(within(rows[1]).getByText('Buildable with color swaps')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Missing pieces' }));
		expect(await screen.findByText('Missing 3')).toBeInTheDocument();
	});
});
