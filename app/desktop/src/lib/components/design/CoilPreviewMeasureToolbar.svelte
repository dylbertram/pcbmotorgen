<!--
  ═══════════════════════════════════════════════════════════════════════
  CoilPreviewMeasureToolbar — the measure-ruler toolbar (mode toggle,
  conditional Reset button, live status prompt).

  Extracted verbatim from CoilPreviewLightbox (kata 426r). There is exactly
  ONE instance in the UI: the lightbox hosts it — the inline collapsed card
  carries no measure UI, because the ruler overlay only draws while the
  lightbox is expanded. All measure state lives in the shared
  CoilPreviewMeasure instance owned by CoilPreview (lib/utils/
  coilPreviewMeasure.svelte.ts) and passed down as a prop, so this
  component is a pure view over that state: clicking here mutates the same
  reactive fields the modal frame's pointer handlers and the renderer read.

  Tool semantics live in the state class: click 1 sets the start point,
  click 2 locks the dimension, click 3 clears it; the Reset button clears
  without a click and toggling the mode off clears too.
  ═══════════════════════════════════════════════════════════════════════
-->
<script lang="ts">
  import { computeMeasureRuler, formatMetresMm } from "../../previewGeometry";
  import type { CoilPreviewMeasure } from "../../utils/coilPreviewMeasure.svelte";

  let { measure, onToggle }: { measure: CoilPreviewMeasure; onToggle?: () => void } = $props();
</script>

<div class="flex items-center gap-3 flex-wrap">
  <div class="flex items-center gap-2">
    <button
      type="button"
      class="px-2 py-0.5 text-xs rounded border transition-colors {measure.mode
        ? 'bg-pink-500/15 border-pink-500 text-pink-300'
        : 'bg-slate-800 border-slate-700 text-slate-300 hover:text-pink-300 hover:border-pink-600'}"
      aria-pressed={measure.mode}
      aria-label="Toggle measure tool"
      onclick={() => onToggle ? onToggle() : measure.toggleMode()}
    >Measure</button>
    {#if measure.mode}
      <button
        type="button"
        class="px-2 py-0.5 text-xs rounded bg-slate-800 border border-slate-700 text-slate-300 hover:text-rose-300 hover:border-rose-600 transition-colors"
        aria-label="Clear measurement"
        onclick={() => measure.clear()}
      >Reset</button>
    {/if}
  </div>
  {#if measure.mode}
    <span class="text-xs text-slate-400" role="status" aria-live="polite">
      {#if measure.p1}
        {#if measure.p2}
          {formatMetresMm(computeMeasureRuler(measure.p1, measure.p2).mm / 1000)} — click again to clear
        {:else}
          {#if measure.cursor}
            {formatMetresMm(computeMeasureRuler(measure.p1, measure.cursor).mm / 1000)} — click to lock
          {:else}
            click to lock the dimension
          {/if}
        {/if}
      {:else}
        click to set the start point
      {/if}
    </span>
  {/if}
</div>
