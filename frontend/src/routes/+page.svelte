<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { session } from '$lib/stores/session.svelte';
	onMount(async () => { await session.load(); void goto(session.authenticated ? '/buildable' : '/unlock'); });
</script>
<p class="redirecting">Opening workshop…</p>
<style>.redirecting { padding:24px; color:var(--ink-muted); }</style>
