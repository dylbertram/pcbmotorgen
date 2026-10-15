<script lang="ts">
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  let { view, layers, onSelect }: { view: CoilPreviewViewState; layers: { idx: number }[]; onSelect?: (layer: number | null) => void } = $props();
  let visible = $derived(layers.filter(({ idx }) => view.isLayerVisible(idx)));
  let step = $derived(visible.length === layers.length ? 0 : visible.length === 1 ? layers.findIndex(({ idx }) => idx === visible[0].idx) + 1 : 0);
  let label = $derived(visible.length === layers.length ? "All" : visible.length === 1 ? `Layer ${visible[0].idx + 1}` : "Custom layers");
  function select(step: number) {
    const layer = step === 0 ? null : layers[step - 1].idx;
    view.layerVisibility = Object.fromEntries(layers.map(({ idx }) => [idx, layer === null || idx === layer]));
    view.coilLayerVisibility = {};
    onSelect?.(layer);
  }
</script>

{#if layers.length}
  <div class="layer-stepper" role="group" aria-label="Layer isolation">
    <input class="layer-slider" type="range" min="0" max={layers.length} step="1" value={step} aria-label="Preview layer" aria-valuetext={label} oninput={(event) => select(Number(event.currentTarget.value))} />
    <div class="layer-step-labels">
      {#each ["All", ...layers.map(({ idx }) => `Layer ${idx + 1}`)] as text, index (text)}
        <button type="button" class:active={label === text} style:left={`${index / layers.length * 100}%`} aria-pressed={label === text} onclick={() => select(index)}>{text}</button>
      {/each}
    </div>
  </div>
{/if}

<style>
  .layer-stepper { flex: 1 1 8rem; max-width: 28rem; min-width: 0; padding: 0 1.5rem; }
  .layer-slider { display: block; appearance: none; width: 100%; height: 1rem; margin: 0; background: transparent; cursor: pointer; }
  .layer-slider::-webkit-slider-runnable-track { height: 2px; border-radius: 1px; background: rgb(var(--slate-600)); }
  .layer-slider::-moz-range-track { height: 2px; border-radius: 1px; background: rgb(var(--slate-600)); }
  .layer-slider::-webkit-slider-thumb { appearance: none; width: 10px; height: 10px; margin-top: -4px; border: 0; border-radius: 50%; background: #34d399; }
  .layer-slider::-moz-range-thumb { width: 10px; height: 10px; border: 0; border-radius: 50%; background: #34d399; }
  .layer-slider:focus-visible { outline: 2px solid #34d399; outline-offset: 3px; }
  .layer-step-labels { position: relative; height: 1rem; margin: 0 5px; }
  .layer-step-labels button { position: absolute; transform: translateX(-50%); white-space: nowrap; font-size: 10px; line-height: 1rem; color: rgb(var(--slate-400)); }
  .layer-step-labels button.active, .layer-step-labels button:hover { color: #34d399; }
  .layer-step-labels button:focus-visible { outline: 2px solid #34d399; outline-offset: 2px; }
</style>
