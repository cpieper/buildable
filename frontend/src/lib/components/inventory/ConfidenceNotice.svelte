<script lang="ts">import type { InventoryWarning } from '$lib/api/types'; let { warnings }: { warnings: InventoryWarning[] } = $props();</script>
{#if warnings.length}<aside role="status" class="notice"><strong>Inventory confidence note</strong><span>Totals include incomplete sets: {warnings.map((warning)=>warning.set_name).join(', ')}.</span></aside>{/if}
<style>.notice{display:grid;gap:3px;padding:10px 12px;margin:14px 0;border-left:4px solid var(--yellow);background:#fff7d8;color:#624d12;font-size:.84rem}</style>
