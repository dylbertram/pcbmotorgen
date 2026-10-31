<script lang="ts">
  let { size = 16 }: { size?: number } = $props();
</script>

<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <path d="M8 4V2h2m4 0h2m4 0h2v2m0 4v2m0 4v2h-2" />
  <circle cx="10" cy="13" r="7" />
  <path d="m5 18-4 5" />
</svg>
