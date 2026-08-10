import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import InventoryPage from './+page.svelte';

describe('inventory page', () => {
	beforeEach(() => vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ total_quantity: 9, warnings: [], items: [
		{ part_num: '3001', part_name: 'Brick 2 x 4', color_id: 4, color_name: 'Bright Red', rgb_hex: 'C91A09', quantity: 5, image_url: null, source_set_nums: ['10497-1'] },
		{ part_num: '3001', part_name: 'Brick 2 x 4', color_id: 85, color_name: 'Dark Bluish Gray', rgb_hex: '6C6E68', quantity: 4, image_url: null, source_set_nums: ['31109-1'] }
	] }), { headers: { 'Content-Type': 'application/json' } })));

	it('expands an inventory part into color rows', async () => {
		render(InventoryPage);
		await fireEvent.click(await screen.findByRole('button', { name: 'Expand Brick 2 x 4' }));
		expect(screen.getAllByText('Bright Red')).toHaveLength(2);
		expect(screen.getAllByText('Dark Bluish Gray')).toHaveLength(2);
	});
});
