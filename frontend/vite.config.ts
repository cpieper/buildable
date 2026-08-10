import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	server: {
		proxy: {
			'/api': 'http://127.0.0.1:8000'
		}
	},
	test: {
		passWithNoTests: true
	},
	plugins: [
		sveltekit({ adapter: adapter() })
	]
});
