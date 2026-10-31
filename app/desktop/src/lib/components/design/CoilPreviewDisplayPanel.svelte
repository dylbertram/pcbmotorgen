<script lang="ts">
  /**
   * Global display options for the shared preview viewers: how copper is
   * drawn (traces or centerlines), whole copper-layer visibility, and the
   * via markers. The motor viewport keeps the global options in View;
   * import previews retain them here while the document menu is disabled.
   */
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";

  let { view, uniqueLayers, viewControlsInMenu = false }: {
    view: CoilPreviewViewState;
    uniqueLayers: { idx: number }[];
    viewControlsInMenu?: boolean;
  } = $props();
  const displayGroup = $props.id();
</script>

<div class="display-controls">
  {#if !viewControlsInMenu}
  <fieldset>
    <legend>Traces</legend>
    <div class="mode-options">
      <label><input type="radio" name={displayGroup} value="traces" bind:group={view.traceMode} />Traces</label>
      <label><input type="radio" name={displayGroup} value="centerlines" bind:group={view.traceMode} />Centerlines</label>
    </div>
  </fieldset>
  {/if}

  {#if uniqueLayers.length > 0}
    <fieldset>
      <legend>Copper layers</legend>
      {#each uniqueLayers as layer (layer.idx)}
        <label class="layer-row" class:hidden-row={!view.isLayerVisible(layer.idx)}>
          <input type="checkbox" checked={view.isLayerVisible(layer.idx)} onchange={() => view.toggleLayer(layer.idx)} aria-label={"Show layer " + layer.idx} />
          <span class="swatch copper"></span><span>Layer {layer.idx + 1}</span>
        </label>
      {/each}
    </fieldset>
  {/if}

  {#if !viewControlsInMenu}
  <fieldset>
    <legend>Overlays</legend>
    <label class="layer-row" class:hidden-row={!view.showTerminals}>
      <input type="checkbox" bind:checked={view.showTerminals} aria-label="Show terminal arrows" />
      <span class="swatch" style:background-color="#34d399"></span><span>Coil-end markers</span>
    </label>
    <label class="layer-row" class:hidden-row={!view.showVias}>
      <input type="checkbox" bind:checked={view.showVias} aria-label="Show vias" />
      <span class="swatch" style:background-color="#fbbf24"></span><span>Vias</span>
    </label>
  </fieldset>
  {/if}
</div>

<style>
  .display-controls { display: grid; gap: 1rem; }
  fieldset { min-width: 0; }
  legend { width: 100%; margin-bottom: 0.35rem; font-size: 0.75rem; font-weight: 600; color: rgb(var(--slate-400)); }
  .layer-row { display: grid; grid-template-columns: 1rem 0.75rem 1fr; align-items: center; gap: 0.6rem; min-height: 2rem; padding: 0.25rem 0.5rem; border-bottom: 1px solid rgb(var(--slate-700)); font-size: 0.75rem; color: rgb(var(--slate-200)); cursor: pointer; }
  .layer-row:hover { background: rgb(var(--slate-800)); }
  .hidden-row { color: rgb(var(--slate-500)); }
  .hidden-row .swatch { opacity: 0.35; }
  .swatch { width: 0.65rem; height: 0.65rem; border-radius: 2px; }
  .copper { background: rgb(var(--slate-300)); }
  input { accent-color: #34d399; }
  input:focus-visible { outline: 2px solid #34d399; outline-offset: 3px; }
  .mode-options { display: flex; gap: 0.75rem; font-size: 0.75rem; color: rgb(var(--slate-200)); }
  .mode-options label { display: flex; align-items: center; gap: 0.35rem; cursor: pointer; }
</style>
