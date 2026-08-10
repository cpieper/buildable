import { expect, type Page } from '@playwright/test';

type ManualSet = {
	set_num: string;
	name: string;
	parts: Array<{ part_num: string; part_name: string; color_id: number; color_name: string; rgb_hex: string; quantity: number }>;
};

export async function unlock(page: Page): Promise<void> {
	await page.goto('/unlock');
	await page.getByLabel('Shared password').fill('build-stuff');
	await page.getByRole('button', { name: 'Unlock' }).click();
	await expect(page.getByRole('main')).toBeVisible();
}

export async function seedSet(page: Page, set: ManualSet): Promise<void> {
	const response = await page.request.post('/api/catalog/manual-sets', { data: set });
	if (response.status() === 422) return;
	expect(response.ok(), await response.text()).toBeTruthy();
}

export async function seedCatalog(page: Page): Promise<void> {
	await seedSet(page, {
		set_num: '10497-1',
		name: 'Galaxy Explorer',
		parts: [{ part_num: '3001', part_name: 'Brick 2 x 4', color_id: 1, color_name: 'Red', rgb_hex: 'c91a09', quantity: 2 }]
	});
	await seedSet(page, {
		set_num: '90000-1',
		name: 'Color Swap Cruiser',
		parts: [{ part_num: '3001', part_name: 'Brick 2 x 4', color_id: 2, color_name: 'Blue', rgb_hex: '0055bf', quantity: 2 }]
	});
}

export async function addOwnedGalaxyExplorer(page: Page): Promise<void> {
	await page.getByRole('link', { name: 'Collection' }).click();
	await page.getByRole('button', { name: 'Add set' }).click();
	await page.getByLabel('Set number or name').fill('10497-1');
	await page.getByRole('option', { name: /10497-1/ }).click();
	await page.getByRole('button', { name: 'Add to collection' }).click();
	await expect(page.getByText('Galaxy Explorer', { exact: true })).toBeVisible();
}
