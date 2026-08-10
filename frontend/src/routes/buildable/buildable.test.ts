import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import BuildablePage from './+page.svelte';

const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
const exact = { set_num: '10497-1', name: 'Galaxy Explorer', year: 2022, theme_name: 'Space', num_parts: 1254, image_url: null, has_local_overrides: false, status: 'exact', counts: { required: 100, exact: 100, color_substitution: 0, equivalence_substitution: 0, missing: 0 }, percent_exact: 100, percent_buildable: 100 };
const swaps = { set_num: '31109-1', name: 'Pirate Ship', year: 2020, theme_name: 'Creator', num_parts: 1264, image_url: null, has_local_overrides: false, status: 'substitution', counts: { required: 100, exact: 94, color_substitution: 6, equivalence_substitution: 0, missing: 0 }, percent_exact: 94, percent_buildable: 100 };
const missing = { set_num: '40501-1', name: 'Missing Set', year: 2021, theme_name: 'Ideas', num_parts: 30, image_url: null, has_local_overrides: false, status: 'missing', counts: { required: 10, exact: 7, color_substitution: 0, equivalence_substitution: 0, missing: 3 }, percent_exact: 70, percent_buildable: 70 };

describe('buildable page', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
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

	it('shows exact sets before color-substitution sets and can reveal missing sets', async () => {
		render(BuildablePage);
		const rows = await screen.findAllByRole('article');
		expect(within(rows[0]).getByText('Exact build')).toBeInTheDocument();
		expect(within(rows[1]).getByText('Buildable with color swaps')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Missing pieces' }));
		expect(await screen.findByText('Missing 3')).toBeInTheDocument();
	});
});
