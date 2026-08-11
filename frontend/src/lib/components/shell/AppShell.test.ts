import { render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import AppShell from './AppShell.svelte';
import MobileNav from './MobileNav.svelte';

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
		expect(
			within(screen.getByRole('link', { name: 'Buildable home' })).getByRole('img', {
				name: 'Buildable'
			})
		).toHaveAttribute('src', expect.stringContaining('buildable-logo.png'));
		expect(within(screen.getByRole('navigation', { name: 'Primary' })).getByRole('link', { name: 'Inventory' })).toHaveAttribute('aria-current', 'page');
	});

	it('marks buildable navigation active for set detail routes on desktop and mobile', () => {
		render(AppShell, { props: { pathname: '/sets/10300-1', children: (() => {}) as never } });
		expect(within(screen.getByRole('navigation', { name: 'Primary' })).getByRole('link', { name: 'Buildable Sets' })).toHaveAttribute('aria-current', 'page');

		render(MobileNav, { props: { pathname: '/sets/10300-1' } });
		expect(within(screen.getAllByRole('navigation', { name: 'Mobile navigation' })[1]).getByRole('link', { name: 'Buildable Sets' })).toHaveAttribute('aria-current', 'page');
	});
});
