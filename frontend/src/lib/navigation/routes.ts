export function safeNext(value: string | null, origin = typeof window === 'undefined' ? 'http://localhost' : window.location.origin): string {
	if (!value) return '/buildable';
	if (!value.startsWith('/')) return '/buildable';
	const path = value.split(/[?#]/, 1)[0];
	let decodedPath: string;
	try { decodedPath = decodeURIComponent(path); } catch { return '/buildable'; }
	if (decodedPath.startsWith('//') || decodedPath.includes('\\')) return '/buildable';
	try {
		const url = new URL(value, origin);
		return url.origin === origin ? `${url.pathname}${url.search}${url.hash}` : '/buildable';
	} catch { return '/buildable'; }
}

export function isRouteActive(href: string, pathname: string): boolean {
	if (href === '/buildable') return pathname === '/buildable' || /^\/sets\/[^/]+$/.test(pathname);
	return pathname === href || pathname.startsWith(`${href}/`);
}
