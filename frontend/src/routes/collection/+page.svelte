<script lang="ts">
	import { apiFetch, ApiError } from '$lib/api/client';
	import type { CatalogSetDetail, CollectionImportSummary, OwnedSet } from '$lib/api/types';
	import OwnedSetRow from '$lib/components/collection/OwnedSetRow.svelte';
	import OwnedSetDialog from '$lib/components/collection/OwnedSetDialog.svelte';
	import MissingPartsEditor from '$lib/components/collection/MissingPartsEditor.svelte';

	let owned = $state<OwnedSet[]>([]);
	let images = $state<Record<string, string | null>>({});
	let adding = $state(false);
	let editing = $state<OwnedSet | null>(null);
	let removing = $state<OwnedSet | null>(null);
	let importing = $state(false);
	let importError = $state('');
	let importSummary = $state<CollectionImportSummary | null>(null);
	const pending = new Map<number, Promise<void>>();

	async function load() {
		owned = await apiFetch<OwnedSet[]>('/api/collection');
		for (const item of owned)
			if (!(item.set_num in images)) {
				void apiFetch<CatalogSetDetail>(`/api/catalog/sets/${item.set_num}`)
					.then((set) => (images = { ...images, [item.set_num]: set.image_url }))
					.catch(() => (images = { ...images, [item.set_num]: null }));
			}
	}

	$effect(() => {
		void load();
	});

	function plural(count: number, singular: string, pluralValue = `${singular}s`) {
		return count === 1 ? singular : pluralValue;
	}

	async function importCsv(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		importing = true;
		importError = '';
		importSummary = null;
		try {
			const body = new FormData();
			body.set('file', file);
			importSummary = await apiFetch<CollectionImportSummary>('/api/collection/import', {
				method: 'POST',
				body
			});
			await load();
		} catch (cause) {
			importError = cause instanceof ApiError ? cause.message : "Couldn't import this CSV.";
		} finally {
			importing = false;
			input.value = '';
		}
	}

	function update(item: OwnedSet, changes: Partial<OwnedSet>) {
		owned = owned.map((row) => (row.id === item.id ? { ...row, ...changes } : row));
		const previous = pending.get(item.id) ?? Promise.resolve();
		const request = previous.then(async () => {
			const next = await apiFetch<OwnedSet>(`/api/collection/${item.id}`, {
				method: 'PATCH',
				body: changes
			});
			owned = owned.map((row) => (row.id === next.id ? next : row));
		});
		pending.set(item.id, request.catch(() => {}));
		return request;
	}

	async function remove() {
		if (!removing) return;
		await apiFetch(`/api/collection/${removing.id}`, { method: 'DELETE' });
		removing = null;
		await load();
	}
</script>

<svelte:head><title>Collection · Buildable</title></svelte:head>
<section class="page-head">
	<div>
		<p class="eyebrow">Workshop collection</p>
		<h1>Owned sets</h1>
		<p>Track what is on the shelf and what is missing from each box.</p>
	</div>
	<div class="page-actions">
		<label class="secondary">
			Import CSV
			<input aria-label="Collection CSV" type="file" accept=".csv,text/csv" onchange={importCsv} />
		</label>
		<button class="primary" onclick={() => (adding = true)}>Add set</button>
	</div>
</section>
{#if importing}<p class="notice" aria-live="polite">Importing collection CSV...</p>{/if}
{#if importSummary}
	<section class="notice success" role="status">
		<p>
			Imported {importSummary.rows_imported}
			{plural(importSummary.rows_imported, 'set row')} adding {importSummary.quantity_added}
			{plural(importSummary.quantity_added, 'copy', 'copies')}.
		</p>
		{#if importSummary.rows_skipped}
			<p>
				Skipped {importSummary.rows_skipped} {plural(importSummary.rows_skipped, 'row')} missing
				from the catalog: {importSummary.missing_set_nums.join(', ')}
			</p>
		{/if}
	</section>
{/if}
{#if importError}<p class="notice error" role="alert">{importError}</p>{/if}
<section class="collection-list">
	{#each owned as item (item.id)}
		<OwnedSetRow
			owned={item}
			imageUrl={images[item.set_num]}
			onEditMissing={() => (editing = item)}
			onUpdate={(changes) => void update(item, changes)}
			onRemove={() => (removing = item)}
		/>
	{/each}
	{#if !owned.length}<p class="empty">No sets yet. Add a cached official set to start your inventory.</p>{/if}
</section>
{#if adding}<OwnedSetDialog onClose={() => (adding = false)} onAdded={load} />{/if}
{#if editing}
	<MissingPartsEditor
		owned={editing}
		onClose={() => (editing = null)}
		onSaved={(total) => {
			owned = owned.map((row) => (row.id === editing?.id ? { ...row, known_missing_total: total } : row));
			editing = null;
		}}
	/>
{/if}
{#if removing}
	<div class="confirm" role="presentation">
		<div role="dialog" aria-modal="true" aria-labelledby="remove-title">
			<h2 id="remove-title">Remove {removing.set_name}?</h2>
			<p>This removes the owned set and its missing-piece records.</p>
			<button onclick={remove}>Remove set</button>
			<button onclick={() => (removing = null)}>Cancel</button>
		</div>
	</div>
{/if}

<style>
	.page-head{display:flex;justify-content:space-between;gap:20px;align-items:end;margin-bottom:20px}.eyebrow{margin:0;color:var(--red);font-size:.72rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase}.page-head h1{margin:3px 0;font-size:2rem;letter-spacing:-.04em}.page-head p:not(.eyebrow){margin:0;color:var(--ink-muted)}.page-actions{display:flex;gap:8px;align-items:center}.primary,.secondary{padding:9px 13px;border:1px solid var(--ink);font-weight:800;border-radius:4px;cursor:pointer}.primary{background:var(--red);color:white}.secondary{position:relative;background:var(--surface);color:var(--ink)}.secondary input{position:absolute;width:1px;height:1px;opacity:0}.notice{margin:0 0 12px;padding:10px 12px;border:1px solid var(--line);background:var(--surface);font-size:.88rem}.notice p{margin:0}.notice p+p{margin-top:4px}.success{border-color:#bad7c0;color:var(--green);background:#edf8ef}.error{border-color:#e3bcc2;color:#8b1c28;background:#fff1f3}.collection-list{border-top:2px solid var(--ink)}.empty{padding:16px 0;color:var(--ink-muted)}.confirm{position:fixed;inset:0;display:grid;place-items:center;padding:16px;background:#17171766}.confirm [role=dialog]{max-width:400px;padding:20px;background:var(--surface);border:1px solid var(--ink);box-shadow:6px 6px #171717}.confirm h2{margin-top:0}.confirm button{margin-right:8px;padding:7px 10px;border:1px solid var(--ink);font-weight:700;background:var(--surface)}.confirm button:first-of-type{background:var(--red);color:white}@media(max-width:719px){.page-head{align-items:start;flex-direction:column}.page-actions{width:100%;display:grid;grid-template-columns:1fr 1fr}.primary,.secondary{text-align:center}}
</style>
