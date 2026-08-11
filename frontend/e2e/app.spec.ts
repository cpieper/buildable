import { expect, test } from '@playwright/test';

import { addOwnedGalaxyExplorer, seedCatalog, unlock } from './fixtures';

async function capture(page: import('@playwright/test').Page, path: string, route: RegExp, heading: string): Promise<void> {
	await expect(page).toHaveURL(route);
	await expect(page.getByRole('heading', { name: heading })).toBeVisible();
	if (/(collection|buildable|match-detail)/.test(path)) {
		const image = page.locator('img').first();
		await expect(image).toBeVisible();
		expect(await image.evaluate((element: HTMLImageElement) => element.complete && element.naturalWidth > 0)).toBe(true);
	}
	await page.screenshot({ path, fullPage: true });
}

test('owned sets become an explainable buildable recommendation', async ({ page }) => {
	await unlock(page);
	await seedCatalog(page);
	await addOwnedGalaxyExplorer(page);

	await page.getByRole('link', { name: 'Buildable Sets' }).click();
	await expect(page.getByText('Buildable with color swaps').first()).toBeVisible();
	await page.getByLabel('Inspect Color Swap Cruiser').click();
	await expect(page.getByText(/Needs Blue/)).toBeVisible();
	await expect(page.getByText(/Use Red/)).toBeVisible();
});

test('recording a known missing piece decreases the available inventory', async ({ page }) => {
	await unlock(page);
	await seedCatalog(page);
	await addOwnedGalaxyExplorer(page);
	const before = await page.request.get('/api/inventory');
	const beforeTotal = (await before.json() as { total_quantity: number }).total_quantity;
	await page.getByLabel('Set actions for Galaxy Explorer').click();
	await page.getByRole('button', { name: /Edit missing pieces/ }).click();
	await page.getByLabel('Search expected pieces').fill('Brick 2 x 4');
	await page.getByRole('button', { name: /Brick 2 x 4.*Red/ }).click();
	await page.getByLabel('Missing quantity').fill('1');
	await page.getByRole('button', { name: 'Save missing piece' }).click();

	await page.goto('/inventory');
	await expect(page.getByText(`${beforeTotal - 1} total parts`)).toBeVisible();
});

test('captures desktop workflow screenshots', async ({ page }) => {
	await page.goto('/unlock');
	await expect(page).toHaveURL(/\/unlock$/);
	await expect(page.getByRole('heading', { name: 'Unlock your workshop.' })).toBeVisible();
	await expect(page.getByLabel('Shared password')).toBeVisible();
	await page.screenshot({ path: 'test-results/screenshots/desktop-unlock.png', fullPage: true });
	await unlock(page);
	await seedCatalog(page);
	await addOwnedGalaxyExplorer(page);
	await page.getByRole('link', { name: 'Collection' }).click();
	await capture(page, 'test-results/screenshots/desktop-collection.png', /\/collection$/, 'Owned sets');
	await page.getByRole('link', { name: 'Inventory' }).click();
	await capture(page, 'test-results/screenshots/desktop-inventory.png', /\/inventory$/, 'Available pieces');
	await page.getByRole('link', { name: 'Buildable Sets' }).click();
	await capture(page, 'test-results/screenshots/desktop-buildable.png', /\/buildable/, 'What can you build?');
	await page.getByLabel('Inspect Color Swap Cruiser').click();
	await capture(page, 'test-results/screenshots/desktop-match-detail.png', /\/sets\/90000-1$/, 'Color Swap Cruiser');
	await page.getByRole('link', { name: 'Settings' }).click();
	await capture(page, 'test-results/screenshots/desktop-settings.png', /\/settings$/, 'Settings');
});
