import { expect, test } from '@playwright/test';

import { addOwnedGalaxyExplorer, seedCatalog, unlock } from './fixtures';

const routes: Record<string, RegExp> = { Collection: /\/collection$/, Inventory: /\/inventory$/, 'Buildable Sets': /\/buildable/, Settings: /\/settings$/ };
const headings: Record<string, string> = { Collection: 'Owned sets', Inventory: 'Available pieces', 'Buildable Sets': 'What can you build?', Settings: 'Settings' };

async function expectLoadedImage(page: import('@playwright/test').Page): Promise<void> {
	const image = page.locator('img').first();
	await expect(image).toBeVisible();
	expect(await image.evaluate((element: HTMLImageElement) => element.complete && element.naturalWidth > 0)).toBe(true);
}

test('mobile navigation reaches every primary screen without horizontal overflow', async ({ page }) => {
	await page.goto('/unlock');
	await expect(page).toHaveURL(/\/unlock$/);
	await expect(page.getByRole('heading', { name: 'Unlock your workshop.' })).toBeVisible();
	await expect(page.getByLabel('Shared password')).toBeVisible();
	await page.screenshot({ path: 'test-results/screenshots/mobile-unlock.png', fullPage: true });
	await unlock(page);
	await seedCatalog(page);
	await addOwnedGalaxyExplorer(page);
	for (const name of ['Collection', 'Inventory', 'Buildable Sets', 'Settings']) {
		await page.getByRole('navigation', { name: 'Mobile navigation' }).getByRole('link', { name }).click();
		await expect(page).toHaveURL(routes[name]);
		await expect(page.getByRole('heading', { name: headings[name] })).toBeVisible();
		if (name === 'Collection' || name === 'Buildable Sets') await expectLoadedImage(page);
		expect(await page.locator('html').evaluate((element) => element.scrollWidth === window.innerWidth)).toBe(true);
		await page.screenshot({ path: `test-results/screenshots/mobile-${name.toLowerCase().replaceAll(' ', '-')}.png`, fullPage: true });
	}
	await page.getByRole('navigation', { name: 'Mobile navigation' }).getByRole('link', { name: 'Buildable Sets' }).click();
	await page.getByLabel('Inspect Color Swap Cruiser').click();
	await expect(page).toHaveURL(/\/sets\/90000-1$/);
	await expect(page.getByRole('heading', { name: 'Color Swap Cruiser' })).toBeVisible();
	await expectLoadedImage(page);
	await expect(page.getByText(/Needs Blue/)).toBeVisible();
	expect(await page.locator('html').evaluate((element) => element.scrollWidth === window.innerWidth)).toBe(true);
	await page.screenshot({ path: 'test-results/screenshots/mobile-match-detail.png', fullPage: true });
});
