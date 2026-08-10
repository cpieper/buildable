import { render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SetDetailPage from './[set_num]/+page.svelte';

describe('set detail page', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
		vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ set_num: '10497-1', name: 'Galaxy Explorer', year: 2022, theme_name: 'Space', num_parts: 1254, image_url: null, external_url: 'https://example.com/set', instructions_url: 'https://example.com/instructions', has_local_overrides: true, status: 'substitution', counts: { required: 100, exact: 98, color_substitution: 2, equivalence_substitution: 0, missing: 0 }, percent_exact: 98, percent_buildable: 100, warnings: [], missing: [], substitutions: [{ required_part: { part_num: '3001', name: 'Brick 2 x 4', image_url: null }, required_color: { id: 4, name: 'Bright Red', rgb_hex: 'C91A09' }, supplied_part: { part_num: '3001', name: 'Brick 2 x 4', image_url: null }, supplied_color: { id: 63, name: 'Dark Blue', rgb_hex: '0A3463' }, quantity: 2, kind: 'color' }] }), { headers: { 'Content-Type': 'application/json' } }));
	});

	it('explains required and supplied colors in Builder Bench detail', async () => {
		render(SetDetailPage);
		expect(await screen.findByRole('heading', { name: /Galaxy Explorer/ })).toBeInTheDocument();
		expect(screen.getByText('Needs Bright Red')).toBeInTheDocument();
		expect(screen.getByText('Use Dark Blue')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Instructions' })).toHaveAttribute('target', '_blank');
	});
});
