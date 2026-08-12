<script lang="ts">
	import type { InventoryItem } from '$lib/api/types';

	let { part, expanded, onToggle }: { part: { part_num:string; part_name:string; total:number; colors:InventoryItem[] }; expanded:boolean; onToggle:()=>void } = $props();
	let thumbnail = $derived(part.colors.find((color) => color.image_url)?.image_url ?? null);
	let previewOpen = $state(false);
</script>

<article class="ledger-row">
	<div class="part">
		<button aria-label={`${expanded ? 'Collapse' : 'Expand'} ${part.part_name}`} onclick={onToggle}>{expanded ? '−' : '+'}</button>
		{#if thumbnail}
			<button class="thumb preview-trigger" type="button" aria-label={`Preview ${part.part_name} image`} aria-haspopup="dialog" onclick={() => previewOpen = true}>
				<img src={thumbnail} alt={`${part.part_name} thumbnail`} loading="lazy" />
			</button>
		{:else}
			<div class="thumb">
				<span aria-hidden="true">{part.part_num.slice(0, 3)}</span>
			</div>
		{/if}
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
{#if previewOpen && thumbnail}
	<div class="preview-backdrop" role="presentation" onclick={(event) => { if (event.target === event.currentTarget) previewOpen = false; }}>
		<div class="preview-dialog" role="dialog" aria-modal="true" aria-labelledby={`part-preview-${part.part_num}`}>
			<header>
				<h2 id={`part-preview-${part.part_num}`}>{part.part_name} image preview</h2>
				<button type="button" aria-label="Close preview" onclick={() => previewOpen = false}>×</button>
			</header>
			<img src={thumbnail} alt={`${part.part_name} preview`} />
		</div>
	</div>
{/if}

<style>
	.ledger-row{display:grid;grid-template-columns:minmax(300px,2fr) .5fr .75fr 1fr;gap:10px;padding:12px 11px;border-bottom:1px solid var(--line);align-items:center}.part{display:flex;align-items:center;gap:10px;min-width:0}.part-text{display:grid;gap:3px;min-width:0}.part strong{line-height:1.2}.part span,small{color:var(--ink-muted);font-size:.78rem}.part button{flex:0 0 auto;width:30px;height:30px;border:1px solid var(--ink);background:var(--surface);font-weight:800}.part .preview-trigger{width:64px;height:64px;padding:0;cursor:zoom-in}.thumb{width:64px;height:64px;flex:0 0 auto;display:grid;place-items:center;border:1px solid var(--line);background:white}.thumb img,.mini-thumb img{width:100%;height:100%;object-fit:contain}.thumb span,.mini-thumb span{color:var(--ink-muted);font-size:.7rem;font-weight:800}.colors{grid-column:1/-1;padding:8px 0 2px 40px}.colors>div{display:grid;grid-template-columns:38px 16px 1fr 36px 1fr;gap:8px;align-items:center;padding:7px 0}.mini-thumb{width:38px;height:38px;display:grid;place-items:center;border:1px solid var(--line);background:white}.colors i{width:14px;height:14px;border:1px solid #555}.preview-backdrop{position:fixed;inset:0;z-index:20;display:grid;place-items:center;padding:18px;background:#17171799}.preview-dialog{width:min(680px,100%);max-height:90vh;padding:16px;border:1px solid var(--ink);border-radius:8px;background:var(--surface);box-shadow:6px 6px #171717}.preview-dialog header{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:12px}.preview-dialog h2{margin:0;font-size:1rem}.preview-dialog header button{width:auto;height:auto;padding:6px 9px;font-size:1.1rem;line-height:1}.preview-dialog>img{display:block;width:100%;max-height:70vh;object-fit:contain;background:white;border:1px solid var(--line);border-radius:6px}@media(max-width:719px){.ledger-row{grid-template-columns:1fr auto}.ledger-row>div:nth-child(3),.ledger-row>div:nth-child(4){grid-column:1/-1;color:var(--ink-muted);font-size:.8rem}.colors{grid-column:1/-1;padding-left:0}.colors>div{grid-template-columns:38px 16px 1fr 36px}.colors small{grid-column:3/-1}.thumb,.part .preview-trigger{width:58px;height:58px}}
</style>
