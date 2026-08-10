import { expect, test } from '@playwright/test';

import { addOwnedGalaxyExplorer, seedCatalog, unlock } from './fixtures';

test('mobile navigation reaches every primary screen without horizontal overflow', async ({ page }) => {
	await page.goto('/unlock');
	await page.screenshot({ path: 'test-results/screenshots/mobile-unlock.png', fullPage: true });
	await unlock(page);
	await seedCatalog(page);
	await addOwnedGalaxyExplorer(page);
	for (const name of ['Collection', 'Inventory', 'Buildable Sets', 'Settings']) {
		await page.getByRole('navigation', { name: 'Mobile navigation' }).getByRole('link', { name }).click();
		await expect(page).toHaveURL(new RegExp(name === 'Buildable Sets' ? '/buildable' : `/${name.toLowerCase()}`));
		expect(await page.locator('html').evaluate((element) => element.scrollWidth === window.innerWidth)).toBe(true);
		await page.screenshot({ path: `test-results/screenshots/mobile-${name.toLowerCase().replaceAll(' ', '-')}.png`, fullPage: true });
	}
	await page.getByRole('navigation', { name: 'Mobile navigation' }).getByRole('link', { name: 'Buildable Sets' }).click();
	await page.getByLabel('Inspect Color Swap Cruiser').click();
	await expect(page.getByText(/Needs Blue/)).toBeVisible();
	expect(await page.locator('html').evaluate((element) => element.scrollWidth === window.innerWidth)).toBe(true);
	await page.screenshot({ path: 'test-results/screenshots/mobile-match-detail.png', fullPage: true });
});
