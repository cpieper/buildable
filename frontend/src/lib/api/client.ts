import type { ApiProblem } from './types';
export class ApiError extends Error { constructor(public readonly status: number, public readonly code: string | undefined, message: string) { super(message); this.name = 'ApiError'; } }
type ApiOptions = Omit<RequestInit, 'body'> & { body?: unknown };
const isAuthPath = (path: string) => path.startsWith('/api/auth/');
function redirectToUnlock() { if (typeof window !== 'undefined') { const next = `${window.location.pathname}${window.location.search}`; window.location.assign(`/unlock?next=${encodeURIComponent(next)}`); } }
export async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<T> {
	const { body, headers, ...request } = options;
	const hasJsonBody = body !== undefined && body !== null && !(body instanceof FormData) && !(body instanceof URLSearchParams) && !(body instanceof Blob);
	const response = await fetch(path, { ...request, credentials: 'include', headers: hasJsonBody ? { 'Content-Type': 'application/json', ...headers } : headers, body: hasJsonBody ? JSON.stringify(body) : (body as BodyInit | null | undefined) });
	if (!response.ok) { let problem: ApiProblem = {}; try { problem = await response.json() as ApiProblem; } catch { /* proxy body was not JSON */ } if (response.status === 401 && !isAuthPath(path)) redirectToUnlock(); throw new ApiError(response.status, problem.code, (problem.detail ?? problem.message ?? response.statusText) || 'Request failed'); }
	if (response.status === 204) return undefined as T;
	return response.json() as Promise<T>;
}
