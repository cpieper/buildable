import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import UnlockPage from '../../../routes/unlock/+page.svelte';

const { goto, page } = vi.hoisted(() => ({ goto: vi.fn(), page: { url: new URL('http://localhost/unlock?next=/inventory?sort=name') } }));
vi.mock('$app/navigation', () => ({ goto }));
vi.mock('$app/state', () => ({ page }));

describe('unlock page', () => {
	beforeEach(() => { goto.mockReset().mockResolvedValue(undefined); page.url = new URL('http://localhost/unlock?next=/inventory?sort=name'); });

	it('brands the unlock page as Buildable', () => {
		render(UnlockPage);
		expect(screen.getByRole('link', { name: 'Buildable' })).toBeInTheDocument();
	});
	it('submits the shared password as JSON and follows a safe next path', async () => {
		const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 })); render(UnlockPage);
		await fireEvent.input(screen.getByLabelText('Shared password'), { target: { value: 'build-stuff' } }); await fireEvent.click(screen.getByRole('button', { name: 'Unlock' }));
		await waitFor(() => expect(goto).toHaveBeenCalledWith('/inventory?sort=name'));
		expect(fetchMock).toHaveBeenCalledWith('/api/auth/login', expect.objectContaining({ method: 'POST', body: JSON.stringify({ password: 'build-stuff' }) }));
	});
	it('falls back to buildable for an unsafe next path', async () => {
		page.url = new URL('http://localhost/unlock?next=%2F%5Cevil.example'); vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 })); render(UnlockPage);
		await fireEvent.input(screen.getByLabelText('Shared password'), { target: { value: 'build-stuff' } }); await fireEvent.click(screen.getByRole('button', { name: 'Unlock' }));
		await waitFor(() => expect(goto).toHaveBeenCalledWith('/buildable'));
	});
	it('shows an inline invalid-password error', async () => {
		vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'Invalid password' }), { status: 401 })); render(UnlockPage);
		await fireEvent.input(screen.getByLabelText('Shared password'), { target: { value: 'wrong' } }); await fireEvent.click(screen.getByRole('button', { name: 'Unlock' }));
		expect(await screen.findByRole('alert')).toHaveTextContent('Invalid password');
	});
});
