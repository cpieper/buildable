import { expect, test } from '@playwright/test';

import { unlock } from './fixtures';

test('mobile navigation reaches every primary screen without horizontal overflow', async ({ page }) => {
	await page.goto('/unlock');
	await page.screenshot({ path: 'test-results/screenshots/mobile-unlock.png', fullPage: true });
	await unlock(page);
	for (const name of ['Collection', 'Inventory', 'Buildable Sets', 'Settings']) {
		await page.getByRole('navigation', { name: 'Mobile navigation' }).getByRole('link', { name }).click();
		await expect(page).toHaveURL(new RegExp(name === 'Buildable Sets' ? '/buildable' : `/${name.toLowerCase()}`));
		expect(await page.locator('html').evaluate((element) => element.scrollWidth === window.innerWidth)).toBe(true);
		await page.screenshot({ path: `test-results/screenshots/mobile-${name.toLowerCase().replaceAll(' ', '-')}.png`, fullPage: true });
	}
});
