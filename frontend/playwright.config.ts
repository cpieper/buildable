import { defineConfig, devices } from '@playwright/test';

const databasePath = '/tmp/buildable-playwright.db';

export default defineConfig({
	testDir: './e2e',
	fullyParallel: false,
	workers: 1,
	reporter: [['list'], ['html', { open: 'never' }]],
	use: {
		baseURL: 'http://127.0.0.1:8000',
		channel: 'chromium',
		trace: 'retain-on-failure',
		screenshot: 'only-on-failure'
	},
	projects: [
		{ name: 'chromium', testMatch: /app\.spec\.ts/, use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } } },
		{ name: 'mobile', testMatch: /mobile\.spec\.ts/, use: { ...devices['iPhone 13'], browserName: 'chromium', viewport: { width: 390, height: 844 } } }
	],
	webServer: {
		command: `rm -f ${databasePath} ${databasePath}-shm ${databasePath}-wal && npm run build && cd ../backend && BUILDABLE_DATABASE_URL=sqlite:////tmp/buildable-playwright.db BUILDABLE_DATA_DIR=/tmp/buildable-playwright-data BUILDABLE_FRONTEND_DIR=../frontend/build BUILDABLE_INITIAL_PASSWORD=build-stuff BUILDABLE_SESSION_SECRET=playwright-session-secret uv run fastapi run app/main.py --host 127.0.0.1 --port 8000`,
		url: 'http://127.0.0.1:8000/api/health',
		reuseExistingServer: false,
		timeout: 120_000
	}
});
