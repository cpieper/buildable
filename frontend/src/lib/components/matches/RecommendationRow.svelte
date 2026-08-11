<script lang="ts">
	import { ArrowRight } from 'lucide-svelte';
	import type { Recommendation } from '$lib/api/types';
	import MatchMeter from './MatchMeter.svelte';
	let { item, onOpen }: { item: Recommendation; onOpen: (setNum: string) => void } = $props();
	const label = (status: Recommendation['status']) => status === 'exact' ? 'Exact build' : status === 'substitution' ? 'Buildable with color swaps' : `Missing ${item.counts.missing}`;
</script>

<article class="recommendation">
	{#if item.image_url}<img src={item.image_url} alt="" />{:else}<div class="image-placeholder" aria-hidden="true">▦</div>{/if}
	<div class="identity"><a href={`/sets/${item.set_num}`}>{item.name}</a><span>{item.set_num} · {item.year ?? 'Year unknown'}{#if item.theme_name} · {item.theme_name}{/if}</span>{#if item.has_local_overrides}<small>Local correction</small>{/if}</div>
	<div class={`status ${item.status}`}>{label(item.status)}</div>
	<MatchMeter counts={item.counts} percentExact={item.percent_exact} percentBuildable={item.percent_buildable} />
	<div class="counts"><span>Exact {item.counts.exact}</span><span>Swaps {item.counts.color_substitution + item.counts.equivalence_substitution}</span>{#if item.counts.missing}<span>Unfilled {item.counts.missing}</span>{/if}</div>
	<button class="open" aria-label={`Inspect ${item.name}`} title="Inspect match" onclick={() => onOpen(item.set_num)}><ArrowRight size={18}/></button>
</article>
<style>
	.recommendation { display:grid; grid-template-columns:52px minmax(180px,1.4fr) minmax(130px,.9fr) minmax(142px,.8fr) minmax(185px,.9fr) 36px; align-items:center; gap:14px; padding:12px 10px; border-bottom:1px solid var(--line); background:var(--surface); }.recommendation img,.image-placeholder { width:52px; height:52px; object-fit:contain; background:#ece6da; border-radius:5px; }.image-placeholder { display:grid; place-items:center; color:var(--ink-muted); }.identity { display:grid; gap:3px; min-width:0; }.identity a { color:var(--ink); font-weight:780; text-decoration:none; }.identity a:hover { text-decoration:underline; }.identity span,.identity small,.counts { color:var(--ink-muted); font-size:.75rem; }.identity small { color:var(--blue); font-weight:700; }.status { font-size:.75rem; font-weight:760; }.status.exact { color:var(--green); }.status.substitution { color:#765300; }.status.missing { color:var(--red); }.counts { display:flex; flex-wrap:wrap; gap:5px 9px; font-variant-numeric:tabular-nums; }.open { display:grid; place-items:center; width:34px; height:34px; padding:0; border:1px solid var(--line); border-radius:5px; color:var(--ink); background:var(--surface); cursor:pointer; }.open:hover { border-color:var(--ink-muted); background:var(--paper); }
	@media(max-width:719px){.recommendation { grid-template-columns:48px 1fr 34px; gap:10px; }.recommendation img,.image-placeholder { width:48px;height:48px; }.status { grid-column:2; }.meter { grid-column:2; }.counts { grid-column:2; }.open { grid-column:3; grid-row:1 / span 4; align-self:center; }}
</style>
