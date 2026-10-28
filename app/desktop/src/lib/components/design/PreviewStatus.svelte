<script lang="ts">
  import type { Snippet } from "svelte";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { MotionStore } from "../../stores/motion.svelte";
  import { stripBoundsDomainMm } from "../../previewGeometry";

  let { config, motion, stats, showSummary = true, children }: {
    config: ConfigStore;
    motion: MotionStore;
    stats: string;
    showSummary?: boolean;
    children?: Snippet;
  } = $props();
  const moverBounds = $derived(stripBoundsDomainMm(config, motion));
</script>

<div class="z-30 flex shrink-0 flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-slate-700 bg-slate-900 px-3 py-2 text-[10px] text-slate-400" role="group" aria-label="Preview status">
  <span class="min-w-0 flex-1 font-mono">Position: {motion.clampedPositionMm.toFixed(1)} mm · Mover extent: {moverBounds.startMm.toFixed(1)} – {moverBounds.endMm.toFixed(1)} mm</span>
  {#if showSummary}<span class="ml-auto shrink-0 text-right" aria-label="Coil geometry summary">{stats}</span>{/if}
  {#if children}{@render children()}{/if}
</div>
