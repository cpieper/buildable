import { describe, expect, it, vi } from 'vitest';
import { apiFetch } from './client';

describe('apiFetch', () => {
	it('sends JSON requests with credentials and returns parsed JSON', async () => {
		const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
			new Response(JSON.stringify({ authenticated: true }), { status: 200 })
		);

		await expect(apiFetch<{ authenticated: boolean }>('/api/example', { method: 'POST', body: { part_num: '3001' } })).resolves.toEqual({ authenticated: true });
		expect(fetchMock).toHaveBeenCalledWith('/api/example', expect.objectContaining({
			credentials: 'include',
			headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
			body: JSON.stringify({ part_num: '3001' })
		}));
	});

	it('turns structured API failures into ApiError', async () => {
		vi.spyOn(globalThis, 'fetch').mockResolvedValue(
			new Response(JSON.stringify({ detail: 'Invalid password', code: 'invalid_password' }), { status: 401 })
		);

		await expect(apiFetch('/api/auth/login', { method: 'POST' })).rejects.toMatchObject({
			status: 401,
			code: 'invalid_password',
			message: 'Invalid password'
		});
	});
});
