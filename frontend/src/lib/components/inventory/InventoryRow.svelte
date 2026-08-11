<script lang="ts">
	import type { InventoryItem } from '$lib/api/types';

	let { part, expanded, onToggle }: { part: { part_num:string; part_name:string; total:number; colors:InventoryItem[] }; expanded:boolean; onToggle:()=>void } = $props();
	let thumbnail = $derived(part.colors.find((color) => color.image_url)?.image_url ?? null);
</script>

<article class="ledger-row">
	<div class="part">
		<button aria-label={`${expanded ? 'Collapse' : 'Expand'} ${part.part_name}`} onclick={onToggle}>{expanded ? '−' : '+'}</button>
		<div class="thumb">
			{#if thumbnail}
				<img src={thumbnail} alt={`${part.part_name} thumbnail`} loading="lazy" />
			{:else}
				<span aria-hidden="true">{part.part_num.slice(0, 3)}</span>
			{/if}
		</div>
		<div class="part-text">
			<strong>{part.part_name}</strong>
			<span>{part.part_num}</span>
		</div>
	</div>
	<div>{part.total}</div>
	<div>{part.colors.length} colors</div>
	<div>{[...new Set(part.colors.flatMap((color)=>color.source_set_nums))].join(', ')}</div>
	{#if expanded}
		<div class="colors">
			{#each part.colors as color}
				<div>
					<div class="mini-thumb">
						{#if color.image_url}
							<img src={color.image_url} alt="" loading="lazy" />
						{:else}
							<span aria-hidden="true">{part.part_num.slice(0, 2)}</span>
						{/if}
					</div>
					<i style={`background:#${color.rgb_hex}`}></i>
					<span>{color.color_name}</span>
					<b>{color.quantity}</b>
					<small>{color.source_set_nums.join(', ')}</small>
				</div>
			{/each}
		</div>
	{/if}
</article>

<style>
	.ledger-row{display:grid;grid-template-columns:minmax(300px,2fr) .5fr .75fr 1fr;gap:10px;padding:12px 11px;border-bottom:1px solid var(--line);align-items:center}.part{display:flex;align-items:center;gap:10px;min-width:0}.part-text{display:grid;gap:3px;min-width:0}.part strong{line-height:1.2}.part span,small{color:var(--ink-muted);font-size:.78rem}.part button{flex:0 0 auto;width:30px;height:30px;border:1px solid var(--ink);background:var(--surface);font-weight:800}.thumb{width:64px;height:64px;flex:0 0 auto;display:grid;place-items:center;border:1px solid var(--line);background:white}.thumb img,.mini-thumb img{width:100%;height:100%;object-fit:contain}.thumb span,.mini-thumb span{color:var(--ink-muted);font-size:.7rem;font-weight:800}.colors{grid-column:1/-1;padding:8px 0 2px 40px}.colors>div{display:grid;grid-template-columns:38px 16px 1fr 36px 1fr;gap:8px;align-items:center;padding:7px 0}.mini-thumb{width:38px;height:38px;display:grid;place-items:center;border:1px solid var(--line);background:white}.colors i{width:14px;height:14px;border:1px solid #555}@media(max-width:719px){.ledger-row{grid-template-columns:1fr auto}.ledger-row>div:nth-child(3),.ledger-row>div:nth-child(4){grid-column:1/-1;color:var(--ink-muted);font-size:.8rem}.colors{grid-column:1/-1;padding-left:0}.colors>div{grid-template-columns:38px 16px 1fr 36px}.colors small{grid-column:3/-1}.thumb{width:58px;height:58px}}
</style>
