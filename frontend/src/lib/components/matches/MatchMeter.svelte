<script lang="ts">
	import type { MatchCounts } from '$lib/api/types';
	let { counts, percentExact, percentBuildable }: { counts: MatchCounts; percentExact: number; percentBuildable: number } = $props();
	const safe = (value: number) => Math.max(0, Math.min(100, value));
</script>

<div class="meter" aria-label={`${Math.round(percentBuildable)}% buildable, ${Math.round(percentExact)}% exact`}>
	<div class="track"><span class="exact" style={`width:${safe(percentExact)}%`}></span><span class="substitution" style={`width:${safe(percentBuildable - percentExact)}%;left:${safe(percentExact)}%`}></span></div>
	<span class="label">{Math.round(percentBuildable)}%</span>
</div>
<style>
	.meter { display:grid; grid-template-columns:minmax(92px, 1fr) 34px; align-items:center; gap:8px; min-width:142px; }
	.track { position:relative; height:8px; overflow:hidden; background:#ddd6ca; border-radius:999px; }
	.track span { position:absolute; inset-block:0; }.exact { left:0; background:var(--green); }.substitution { background:var(--yellow); }.label { font-variant-numeric:tabular-nums; font-size:.75rem; font-weight:750; text-align:right; }
</style>
