import { expect, test } from '@playwright/test';

import { addOwnedGalaxyExplorer, seedCatalog, unlock } from './fixtures';

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
	await page.screenshot({ path: 'test-results/screenshots/desktop-unlock.png', fullPage: true });
	await unlock(page);
	await seedCatalog(page);
	await page.getByRole('link', { name: 'Collection' }).click();
	await page.screenshot({ path: 'test-results/screenshots/desktop-collection.png', fullPage: true });
	await page.getByRole('link', { name: 'Inventory' }).click();
	await page.screenshot({ path: 'test-results/screenshots/desktop-inventory.png', fullPage: true });
	await page.getByRole('link', { name: 'Buildable Sets' }).click();
	await page.screenshot({ path: 'test-results/screenshots/desktop-buildable.png', fullPage: true });
	await page.getByLabel('Inspect Color Swap Cruiser').click();
	await page.screenshot({ path: 'test-results/screenshots/desktop-match-detail.png', fullPage: true });
	await page.getByRole('link', { name: 'Settings' }).click();
	await page.screenshot({ path: 'test-results/screenshots/desktop-settings.png', fullPage: true });
});
