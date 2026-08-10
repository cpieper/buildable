import { render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import AppShell from './AppShell.svelte';

vi.mock('$lib/stores/session.svelte', () => ({
	session: {
		authenticated: true,
		loading: false,
		load: vi.fn(),
		login: vi.fn(),
		logout: vi.fn()
	}
}));

describe('AppShell', () => {
	it('marks the current workshop section in primary navigation', () => {
		render(AppShell, {
			props: {
				pathname: '/inventory',
				children: (() => {}) as never
			}
		});

		expect(screen.getByRole('navigation', { name: 'Primary' })).toBeInTheDocument();
		expect(within(screen.getByRole('navigation', { name: 'Primary' })).getByRole('link', { name: 'Inventory' })).toHaveAttribute('aria-current', 'page');
	});
});
