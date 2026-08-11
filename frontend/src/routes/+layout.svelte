<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import AppShell from '$lib/components/shell/AppShell.svelte';
	import { session } from '$lib/stores/session.svelte';
	import '../app.css';

	let { children } = $props();
	$effect(() => { if (browser) void session.load(); });
	$effect(() => { if (!browser || session.loading) return; if (page.url.pathname === '/') { void goto(session.authenticated ? '/buildable' : '/unlock'); return; } if (page.url.pathname !== '/unlock' && !session.authenticated) void goto(`/unlock?next=${encodeURIComponent(`${page.url.pathname}${page.url.search}`)}`); });
</script>

{#if page.url.pathname === '/unlock'}
	{@render children()}
{:else if session.authenticated}
	<AppShell pathname={page.url.pathname}>{@render children()}</AppShell>
{/if}
