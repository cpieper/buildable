import { describe, expect, it } from 'vitest';
import { isRouteActive, safeNext } from './routes';

describe('safeNext', () => {
	it.each(['/inventory?sort=name#top', '/buildable', '/sets/10300-1'])('preserves local destinations: %s', (next) => {
		expect(safeNext(next)).toBe(next);
	});

	it.each(['/inventory?filter=%5C', '/inventory#section-%5C'])('preserves backslashes in local query and hash values: %s', (next) => {
		expect(safeNext(next)).toBe(next);
	});

	it.each(['//evil.example', '/\\evil.example', '/%5c%5cevil.example', '/inventory%5Cevil.example', 'https://evil.example', 'https:%2f%2fevil.example'])('rejects unsafe destinations: %s', (next) => {
		expect(safeNext(next)).toBe('/buildable');
	});
});

describe('isRouteActive', () => {
	it('keeps ordinary sections active for nested routes', () => {
		expect(isRouteActive('/inventory', '/inventory/parts')).toBe(true);
		expect(isRouteActive('/collection', '/collections')).toBe(false);
	});

	it('activates Buildable Sets for actual set detail routes only', () => {
		expect(isRouteActive('/buildable', '/buildable')).toBe(true);
		expect(isRouteActive('/buildable', '/sets/10300-1')).toBe(true);
		expect(isRouteActive('/buildable', '/buildable/10300-1')).toBe(false);
	});
});
