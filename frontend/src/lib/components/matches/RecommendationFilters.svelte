<script lang="ts">
	import type { MatchStatus } from '$lib/api/types';
	let { statuses = $bindable(), maxPieces = $bindable(), theme = $bindable(), yearFrom = $bindable(), yearTo = $bindable(), sort = $bindable(), themes, onChange }: { statuses: Record<MatchStatus, boolean>; maxPieces: string; theme: string; yearFrom: string; yearTo: string; sort: string; themes: string[]; onChange: () => void } = $props();
</script>
<div class="filters" aria-label="Recommendation filters">
	<fieldset><legend>Status</legend>{#each [['exact','Exact builds'],['substitution','Color swaps'],['missing','Missing pieces']] as pair}<label><input type="checkbox" bind:checked={statuses[pair[0] as MatchStatus]} onchange={onChange}/>{pair[1]}</label>{/each}</fieldset>
	<label>Theme<select bind:value={theme} onchange={onChange}><option value="">All themes</option>{#each themes as value}<option>{value}</option>{/each}</select></label>
	<label>From year<input type="number" min="1900" max="2100" bind:value={yearFrom} onchange={onChange}/></label>
	<label>To year<input type="number" min="1900" max="2100" bind:value={yearTo} onchange={onChange}/></label>
	<label>Maximum pieces<input type="number" min="0" bind:value={maxPieces} onchange={onChange}/></label>
	<label>Sort<select bind:value={sort} onchange={onChange}><option value="buildability">Best match</option><option value="pieces">Piece count</option><option value="year">Year</option><option value="mismatches">Fewest swaps</option><option value="missing">Fewest missing</option></select></label>
</div>
<style>.filters { display:flex; flex-wrap:wrap; gap:10px 14px; align-items:end; padding:12px; border:1px solid var(--line); background:var(--surface); }.filters label { display:grid; gap:4px; color:var(--ink-muted); font-size:.72rem; font-weight:700; }.filters input,.filters select { min-height:33px; max-width:130px; border:1px solid var(--line); border-radius:4px; padding:4px 7px; background:white; color:var(--ink); }fieldset { display:flex; flex-wrap:wrap; gap:7px; margin:0; padding:0; border:0; }fieldset legend { padding:0 0 4px; color:var(--ink-muted); font-size:.72rem; font-weight:700; }fieldset label { display:flex; align-items:center; gap:4px; }fieldset input { min-height:auto; }@media(max-width:719px){.filters { display:grid; grid-template-columns:1fr 1fr; }.filters fieldset { grid-column:1/-1; }.filters input,.filters select { width:100%; max-width:none; }}</style>
