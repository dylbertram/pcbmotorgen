<script lang="ts">
  import { PHASE_COLORS } from "./coilPreviewCanvas";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import type { CadGeometry } from "../../types";
  import type { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";
  import SelectionAssignmentMenu from "./SelectionAssignmentMenu.svelte";
  import { selectableTraces } from "../../cadSelection";

  let { name, colorIdx, label, visibilityLabel, visible, onToggle, layers, view,
    geometry, selection, disabled = false }: {
    name: string; colorIdx: number; label: string; visibilityLabel: string;
    visible: boolean; onToggle: () => void;
    layers: { idx: number }[]; view: CoilPreviewViewState;
    geometry?: CadGeometry | null; selection?: CadSelectionTool; disabled?: boolean;
  } = $props();
  let unavailable = $derived(disabled || !geometry || !selection?.selected.length);
  function move(layer?: number) {
    if (unavailable) return;
    const destinationLayers = layer === undefined
      ? [...new Set(selectableTraces(geometry!).filter((trace) => selection!.selected.includes(trace.id)).map((trace) => trace.layer))]
      : [layer];
    selection?.apply(name, layer === undefined ? "" : String(layer));
    if (!visible) onToggle();
    for (const destinationLayer of destinationLayers) {
      view.layerVisibility = { ...view.layerVisibility, [destinationLayer]: true };
      view.showCoilLayer(name, destinationLayer);
    }
  }
</script>

<div role="group" aria-label={label} class="coil-layer-group">
  <SelectionAssignmentMenu tool={selection} {geometry} {disabled} destination={{ coil: name }} onMove={() => move()}>
    <div class="row" class:hidden-row={!visible}>
      <input type="checkbox" checked={visible} onchange={onToggle} aria-label={visibilityLabel} />
      <span class="swatch" style:background-color={PHASE_COLORS[colorIdx % PHASE_COLORS.length]}></span>
      <button type="button" disabled={unavailable} onclick={() => move()} aria-label={`Move selection to ${label}`} title={`Move selected segments to ${label}; keep their copper layers.`}>{label}</button>
    </div>
  </SelectionAssignmentMenu>
  <div class="nested">
    {#each layers as layer (layer.idx)}
      <SelectionAssignmentMenu tool={selection} {geometry} {disabled} destination={{ coil: name, layer: layer.idx }} onMove={() => move(layer.idx)}>
        <div class="row" class:hidden-row={!visible || !view.isLayerVisible(layer.idx) || !view.isCoilLayerVisible(name, layer.idx)}>
          <input type="checkbox" checked={view.isCoilLayerVisible(name, layer.idx)} onchange={() => view.toggleCoilLayer(name, layer.idx)} aria-label={`Show ${name}, layer ${layer.idx + 1}`} />
          <span class="branch" aria-hidden="true"></span>
          <button type="button" disabled={unavailable} onclick={() => move(layer.idx)} aria-label={`Move selection to ${name}, layer ${layer.idx + 1}`} title={`Move selected segments to ${name}, layer ${layer.idx + 1}.`}>Layer {layer.idx + 1}</button>
        </div>
      </SelectionAssignmentMenu>
    {/each}
  </div>
</div>

<style>
  .row { display: grid; grid-template-columns: 1rem .75rem 1fr; gap: .6rem; align-items: center; min-height: 2rem; padding: .25rem .5rem; border-bottom: 1px solid rgb(var(--slate-700)); font-size: .75rem; color: rgb(var(--slate-200)); }
  .row:hover { background: rgb(var(--slate-800)); }
  .nested { margin-left: 1.25rem; border-left: 1px solid rgb(var(--slate-700)); }
  .hidden-row { color: rgb(var(--slate-500)); }
  .swatch { width: .65rem; height: .65rem; border-radius: 2px; }
  .hidden-row .swatch { opacity: .35; }
  .branch { width: .65rem; border-bottom: 1px solid rgb(var(--slate-600)); }
  button { min-width: 0; text-align: left; padding: .25rem 0; color: inherit; border-radius: 2px; overflow-wrap: anywhere; }
  button:not(:disabled) { cursor: pointer; }
  button:not(:disabled):hover { color: #34d399; }
  input { accent-color: #34d399; cursor: pointer; }
  button:focus-visible, input:focus-visible { outline: 2px solid #34d399; outline-offset: 2px; }
</style>
