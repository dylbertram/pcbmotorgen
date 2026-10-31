<script lang="ts">
  import { PHASE_COLORS } from "./coilPreviewCanvas";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import type { CadGeometry } from "../../types";
  import type { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";
  import SelectionAssignmentMenu from "./SelectionAssignmentMenu.svelte";

  let { layer, phases, view, geometry, selection, disabled = false }: {
    layer: number;
    phases: { name: string; label: string; colorIdx: number; visible: boolean; onShow: () => void }[];
    view: CoilPreviewViewState;
    geometry?: CadGeometry | null;
    selection?: CadSelectionTool;
    disabled?: boolean;
  } = $props();
  let unavailable = $derived(disabled || !geometry || !selection?.selected.length);

  function move(phase: (typeof phases)[number]) {
    if (unavailable) return;
    selection?.apply(phase.name, String(layer));
    if (!phase.visible) phase.onShow();
    view.layerVisibility = { ...view.layerVisibility, [layer]: true };
    view.showCoilLayer(phase.name, layer);
  }
</script>

<div role="group" aria-label={`Layer ${layer + 1}`}>
  <label class="row" class:hidden-row={!view.isLayerVisible(layer)}>
    <input type="checkbox" checked={view.isLayerVisible(layer)} onchange={() => view.toggleLayer(layer)} aria-label={`Show layer ${layer}`} />
    <span class="swatch copper"></span><span>Layer {layer + 1}</span>
  </label>
  <div class="nested">
    {#each phases as phase (phase.name)}
      <SelectionAssignmentMenu tool={selection} {geometry} {disabled} destination={{ coil: phase.name, layer }} onMove={() => move(phase)}>
        <div class="row" class:hidden-row={!phase.visible || !view.isLayerVisible(layer) || !view.isCoilLayerVisible(phase.name, layer)}>
          <input type="checkbox" checked={view.isCoilLayerVisible(phase.name, layer)} onchange={() => view.toggleCoilLayer(phase.name, layer)} aria-label={`Show ${phase.name}, layer ${layer + 1}`} />
          <span class="swatch" style:background-color={PHASE_COLORS[phase.colorIdx % PHASE_COLORS.length]}></span>
          <button type="button" disabled={unavailable} onclick={() => move(phase)} aria-label={`Move selection to ${phase.name}, layer ${layer + 1}`} title={`Move selected segments to ${phase.name}, layer ${layer + 1}.`}>{phase.label}</button>
        </div>
      </SelectionAssignmentMenu>
    {/each}
  </div>
</div>

<style>
  .row { display: grid; grid-template-columns: 1rem .75rem 1fr; gap: .6rem; align-items: center; min-height: 2rem; padding: .25rem .5rem; border-bottom: 1px solid rgb(var(--slate-700)); font-size: .75rem; color: rgb(var(--slate-200)); }
  label.row { cursor: pointer; }
  .row:hover { background: rgb(var(--slate-800)); }
  .nested { margin-left: 1.25rem; border-left: 1px solid rgb(var(--slate-700)); }
  .hidden-row { color: rgb(var(--slate-500)); }
  .swatch { width: .65rem; height: .65rem; border-radius: 2px; }
  .hidden-row .swatch { opacity: .35; }
  .copper { background: rgb(var(--slate-300)); }
  button { min-width: 0; text-align: left; padding: .25rem 0; color: inherit; border-radius: 2px; overflow-wrap: anywhere; }
  button:not(:disabled) { cursor: pointer; }
  button:not(:disabled):hover { color: #34d399; }
  input { accent-color: #34d399; cursor: pointer; }
  button:focus-visible, input:focus-visible { outline: 2px solid #34d399; outline-offset: 2px; }
</style>
