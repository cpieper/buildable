<script lang="ts">
	import logoUrl from '$lib/assets/buildable-logo.png';

	let {
		size = 'compact',
		alt = 'Buildable'
	}: {
		size?: 'hero' | 'compact';
		alt?: string;
	} = $props();
</script>

<img class={`brand-logo ${size}`} src={logoUrl} {alt} />

<style>
	.brand-logo {
		display: block;
		width: 100%;
		height: auto;
		object-fit: contain;
	}

	.hero {
		max-width: 236px;
		margin: 0 auto;
	}

	.compact {
		max-width: 148px;
	}
</style>
