<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { ApiError } from '$lib/api/client';
	import { session } from '$lib/stores/session.svelte';
	let password = $state(''); let error = $state(''); let submitting = $state(false);
	function safeNext(value: string | null) { return value?.startsWith('/') && !value.startsWith('//') ? value : '/buildable'; }
	async function unlock() { error = ''; submitting = true; try { await session.login(password); await goto(safeNext(page.url.searchParams.get('next'))); } catch (cause) { error = cause instanceof ApiError ? cause.message : 'Unable to unlock the workshop.'; } finally { submitting = false; } }
</script>
<svelte:head><title>Unlock · What2Build</title></svelte:head>
<main class="unlock-page"><form onsubmit={(event) => { event.preventDefault(); void unlock(); }}><a class="wordmark" href="/unlock">What2Build</a><p>Unlock your workshop.</p><label for="shared-password">Shared password</label><input id="shared-password" name="password" type="password" bind:value={password} autocomplete="current-password" required />{#if error}<p class="error" role="alert">{error}</p>{/if}<button type="submit" disabled={submitting}>{submitting ? 'Unlocking…' : 'Unlock'}</button></form></main>
<style>.unlock-page { display:grid; min-height:100dvh; place-items:center; padding:20px; }form { width:min(100%,360px); padding:24px; border:1px solid var(--line); border-radius:8px; background:var(--surface); }.wordmark { color:var(--ink); font-size:1.35rem; font-weight:800; letter-spacing:-.04em; text-decoration:none; }p { color:var(--ink-muted); font-size:.9rem; }label { display:block; margin:24px 0 6px; font-size:.875rem; font-weight:700; }input { width:100%; min-height:42px; padding:8px 10px; border:1px solid var(--ink-soft); border-radius:4px; background:white; color:var(--ink); }button { width:100%; min-height:42px; margin-top:16px; border:0; border-radius:4px; background:var(--red); color:white; font-weight:750; cursor:pointer; }button:disabled { opacity:.6; cursor:wait; }.error { margin:10px 0 0; color:var(--red); font-weight:650; }</style>
