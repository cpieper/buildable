import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { setMockSetNum } from '../../test/mock-page.svelte';

vi.mock('$app/state', async () => await import('../../test/mock-page.svelte'));
import SetDetailPage from './[set_num]/+page.svelte';

describe('set detail page', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
		setMockSetNum('10497-1');
		vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ set_num: '10497-1', name: 'Galaxy Explorer', year: 2022, theme_name: 'Space', num_parts: 1254, image_url: null, external_url: 'https://example.com/set', instructions_url: 'https://example.com/instructions', has_local_overrides: true, status: 'substitution', counts: { required: 100, exact: 98, color_substitution: 2, equivalence_substitution: 0, missing: 0 }, percent_exact: 98, percent_buildable: 100, warnings: [], missing: [], substitutions: [{ required_part: { part_num: '3001', name: 'Brick 2 x 4', image_url: null }, required_color: { id: 4, name: 'Bright Red', rgb_hex: 'C91A09' }, supplied_part: { part_num: '3001', name: 'Brick 2 x 4', image_url: null }, supplied_color: { id: 63, name: 'Dark Blue', rgb_hex: '0A3463' }, quantity: 2, kind: 'color' }] }), { headers: { 'Content-Type': 'application/json' } }));
	});

	it('reloads with the reactive route parameter instead of retaining the prior match', async () => {
		vi.mocked(globalThis.fetch).mockImplementation(async (input) => new Response(JSON.stringify({ set_num: String(input).endsWith('31109-1') ? '31109-1' : '10497-1', name: String(input).endsWith('31109-1') ? 'Pirate Ship' : 'Galaxy Explorer', year: 2022, theme_name: 'Space', num_parts: 1, image_url: null, external_url: null, instructions_url: null, has_local_overrides: false, status: 'exact', counts: { required: 1, exact: 1, color_substitution: 0, equivalence_substitution: 0, missing: 0 }, percent_exact: 100, percent_buildable: 100, warnings: [], missing: [], substitutions: [] }), { headers: { 'Content-Type': 'application/json' } }));
		render(SetDetailPage);
		expect(await screen.findByRole('heading', { name: 'Galaxy Explorer' })).toBeInTheDocument();
		setMockSetNum('31109-1');
		expect(await screen.findByRole('heading', { name: 'Pirate Ship' })).toBeInTheDocument();
	});

	it('explains required and supplied colors in Builder Bench detail', async () => {
		render(SetDetailPage);
		expect(await screen.findByRole('heading', { name: /Galaxy Explorer/ })).toBeInTheDocument();
		expect(screen.getByText('Needs Bright Red')).toBeInTheDocument();
		expect(screen.getByText('Use Dark Blue')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Instructions' })).toHaveAttribute('target', '_blank');
	});

	it('shows a catalog image and required-color swatch for missing pieces', async () => {
		vi.mocked(globalThis.fetch).mockImplementation(async (input) => {
			const url = String(input);
			if (url.startsWith('/api/matches/')) return new Response(JSON.stringify({ set_num: '10497-1', name: 'Galaxy Explorer', year: 2022, theme_name: 'Space', num_parts: 1254, image_url: null, external_url: null, instructions_url: null, has_local_overrides: false, status: 'missing', counts: { required: 2, exact: 0, color_substitution: 0, equivalence_substitution: 0, missing: 2 }, percent_exact: 0, percent_buildable: 0, warnings: [], substitutions: [], missing: [{ part_num: '3001', part_name: 'Brick 2 x 4', color_id: 4, color_name: 'Bright Red', quantity: 2 }] }), { headers: { 'Content-Type': 'application/json' } });
			if (url === '/api/catalog/sets/10497-1') return new Response(JSON.stringify({ set_num: '10497-1', name: 'Galaxy Explorer', year: 2022, theme_name: 'Space', num_parts: 1254, image_url: null, external_url: null, instructions_url: null, has_local_overrides: false, parts: [{ part_num: '3001', part_name: 'Brick 2 x 4', color_id: 4, color_name: 'Bright Red', rgb_hex: 'C91A09', quantity: 2, is_spare: false, source_kind: 'set', image_url: 'https://example.com/3001.png' }] }), { headers: { 'Content-Type': 'application/json' } });
			return new Response(JSON.stringify({}), { headers: { 'Content-Type': 'application/json' } });
		});
		render(SetDetailPage);
		await fireEvent.click(await screen.findByRole('tab', { name: /Missing pieces/ }));
		const image = await screen.findByRole('img', { name: 'Brick 2 x 4' });
		expect(image).toHaveAttribute('src', 'https://example.com/3001.png');
		expect(screen.getByLabelText('Required color Bright Red')).toHaveStyle({ backgroundColor: 'rgb(201, 26, 9)' });
	});
});
