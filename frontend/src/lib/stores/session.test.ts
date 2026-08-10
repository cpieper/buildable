import { describe, expect, it, vi } from 'vitest';
import { session } from './session.svelte';

describe('session', () => {
	it('does not let a stale unauthenticated load undo a successful login', async () => {
		let resolveSession!: (response: Response) => void;
		const pendingSession = new Promise<Response>((resolve) => { resolveSession = resolve; });
		vi.spyOn(globalThis, 'fetch')
			.mockReturnValueOnce(pendingSession)
			.mockResolvedValueOnce(new Response(null, { status: 204 }));

		const loading = session.load();
		await session.login('build-stuff');
		resolveSession(new Response(JSON.stringify({ authenticated: false }), { status: 200 }));
		await loading;

		expect(session.authenticated).toBe(true);
	});
});
