<script lang="ts">
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import CoilLayerTreeGroup from "./CoilLayerTreeGroup.svelte";
  import LayerPhaseTreeGroup from "./LayerPhaseTreeGroup.svelte";
  import CoilPreviewDisplayPanel from "./CoilPreviewDisplayPanel.svelte";
  import type { CadGeometry } from "../../types";
  import type { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";

  let { view, uniquePhases, uniqueLayers, hasPolePitchData, hasBandWidthData,
    hasPoleRegionData, poleRegionPhases, showMotorControls = true, viewControlsInMenu = false,
    coils = [], isCoilVisible, onToggleCoil, geometry, selection, assignmentDisabled = false }: {
    view: CoilPreviewViewState;
    uniquePhases: { idx: number; name: string; colorIdx: number }[];
    uniqueLayers: { idx: number }[];
    hasPolePitchData: boolean;
    hasBandWidthData: boolean;
    hasPoleRegionData: boolean;
    poleRegionPhases: string[];
    showMotorControls?: boolean;
    viewControlsInMenu?: boolean;
    coils?: { name: string; colorIdx: number }[];
    isCoilVisible?: (name: string) => boolean;
    onToggleCoil?: (name: string) => void;
    geometry?: CadGeometry | null;
    selection?: CadSelectionTool;
    assignmentDisabled?: boolean;
  } = $props();
  const sortId = $props.id();
  const layerPhases = $derived([
    ...uniquePhases.map(ph => ({
      name: ph.name, label: `Phase ${ph.name}`, colorIdx: ph.colorIdx,
      visible: view.isPhaseVisible(ph.idx), onShow: () => { view.phaseVisibility[ph.idx] = true; },
    })),
    ...(isCoilVisible && onToggleCoil ? coils.map(coil => ({
      name: coil.name, label: `${/^[ABC]$/.test(coil.name) ? 'Phase' : 'Coil'} ${coil.name}`, colorIdx: coil.colorIdx,
      visible: isCoilVisible(coil.name), onShow: () => { if (!isCoilVisible?.(coil.name)) onToggleCoil?.(coil.name); },
    })) : []),
  ]);
</script>

<div class="layer-controls">
  <div class="sort-row">
    <span id={`${sortId}-label`}>Sort by</span>
    <div class="sort-options" role="radiogroup" aria-labelledby={`${sortId}-label`}>
      <label class={view.layerSortMode === "phases" ? "active text-emerald-300" : ""}><input type="radio" name={sortId} value="phases" bind:group={view.layerSortMode} />Phases</label>
      <label class={view.layerSortMode === "layers" ? "active text-emerald-300" : ""}><input type="radio" name={sortId} value="layers" bind:group={view.layerSortMode} />Layers</label>
    </div>
  </div>
  {#if view.layerSortMode === "phases"}
  {#if uniquePhases.length > 0}
    <fieldset aria-label="Phase visibility">
      {#each uniquePhases as ph (ph.idx)}
        <CoilLayerTreeGroup name={ph.name} colorIdx={ph.colorIdx} label={`Phase ${ph.name}`} visibilityLabel={`Show phase ${ph.name}`}
          visible={view.isPhaseVisible(ph.idx)} onToggle={() => view.phaseVisibility[ph.idx] = !view.isPhaseVisible(ph.idx)}
          layers={uniqueLayers} {view} {geometry} {selection} disabled={assignmentDisabled} />
      {/each}
    </fieldset>
  {/if}

  {#if coils.length > 0 && isCoilVisible && onToggleCoil}
    <fieldset aria-label="Coil visibility">
      {#each coils as coil (coil.name)}
        <CoilLayerTreeGroup name={coil.name} colorIdx={coil.colorIdx} label={`${/^[ABC]$/.test(coil.name) ? 'Phase' : 'Coil'} ${coil.name}`} visibilityLabel={`Coil ${coil.name}`}
          visible={isCoilVisible(coil.name)} onToggle={() => onToggleCoil?.(coil.name)}
          layers={uniqueLayers} {view} {geometry} {selection} disabled={assignmentDisabled} />
      {/each}
    </fieldset>
  {/if}
  {:else}
    <fieldset aria-label="Copper layers">
      {#each uniqueLayers as layer (layer.idx)}
        <LayerPhaseTreeGroup layer={layer.idx} phases={layerPhases} {view} {geometry} {selection} disabled={assignmentDisabled} />
      {/each}
    </fieldset>
  {/if}

  {#if !viewControlsInMenu}
    <CoilPreviewDisplayPanel {view} />
  {/if}

  {#if !viewControlsInMenu && (hasPolePitchData || hasBandWidthData || hasPoleRegionData)}
  <fieldset>
    <legend>Overlays</legend>
    {#if hasPolePitchData}
      <label class="layer-row" class:hidden-row={!view.showPolePitch}>
        <input type="checkbox" bind:checked={view.showPolePitch} aria-label="Show pole-pitch dimension ruler" />
        <span class="swatch" style:background-color="#a5b4fc"></span><span>Pole pitch</span>
      </label>
    {/if}
    {#if hasBandWidthData}
      <label class="layer-row" class:hidden-row={!view.showBandWidths}>
        <input type="checkbox" bind:checked={view.showBandWidths} aria-label="Show band-width diagnostics" />
        <span class="swatch" style:background-color="#34d399"></span><span>Conductor band widths</span>
      </label>
    {/if}
    {#if hasPoleRegionData}
      <label class="layer-row" class:hidden-row={!view.showPoleRegions}>
        <input type="checkbox" bind:checked={view.showPoleRegions} aria-label="Show pole regions" />
        <span class="swatch regions"></span><span>Pole regions</span>
      </label>
    {/if}
  </fieldset>
  {/if}

  {#if hasPoleRegionData}
    <fieldset>
      <legend>Pole region phase</legend>
      <select aria-label="Pole regions phase" bind:value={view.poleRegionPhase} disabled={!view.showPoleRegions}>
        <option value="">All phases</option>
        {#each poleRegionPhases as phase (phase)}<option value={phase}>{phase}</option>{/each}
      </select>
    </fieldset>
  {/if}

  {#if showMotorControls && !viewControlsInMenu}
    <fieldset>
      <legend>Waveform</legend>
      <label class="layer-row" class:hidden-row={!view.showWaveform} title="Show or hide the phase holding-force waves below the mover slider.">
        <input type="checkbox" bind:checked={view.showWaveform} aria-label="Show phase waveform" />
        <span class="col-span-2">Phase waveform</span>
      </label>
    </fieldset>
    <fieldset>
      <legend>Pattern</legend>
      <label class="layer-row">
        <input type="checkbox" bind:checked={view.oneSection} aria-label="Show only one repeating section of the pattern" />
        <span class="col-span-2">One electrical period</span>
      </label>
    </fieldset>
  {/if}
</div>

<style>
  .layer-controls { display: grid; gap: 1rem; }
  .sort-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem; font-size: .75rem; color: rgb(var(--slate-400)); }
  .sort-options { display: inline-flex; padding: .125rem; border: 1px solid rgb(var(--slate-700)); border-radius: .25rem; color: rgb(var(--slate-300)); }
  .sort-options label { position: relative; padding: .3rem .5rem; border-radius: .125rem; cursor: pointer; }
  .sort-options label:hover { background: rgb(var(--slate-800)); }
  .sort-options label.active { background: rgb(var(--slate-800)); }
  .sort-options label:focus-within { outline: 2px solid #34d399; outline-offset: 2px; }
  .sort-options input { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: pointer; }
  fieldset { min-width: 0; }
  legend { width: 100%; margin-bottom: 0.35rem; font-size: 0.75rem; font-weight: 600; color: rgb(var(--slate-400)); }
  .layer-row { display: grid; grid-template-columns: 1rem 0.75rem 1fr; align-items: center; gap: 0.6rem; min-height: 2rem; padding: 0.25rem 0.5rem; border-bottom: 1px solid rgb(var(--slate-700)); font-size: 0.75rem; color: rgb(var(--slate-200)); cursor: pointer; }
  .layer-row:hover { background: rgb(var(--slate-800)); }
  .hidden-row { color: rgb(var(--slate-500)); }
  .hidden-row .swatch { opacity: 0.35; }
  .swatch { width: 0.65rem; height: 0.65rem; border-radius: 2px; }
  .regions { background: linear-gradient(90deg, #f87171 50%, #60a5fa 50%); }
  input { accent-color: #34d399; }
  input:focus-visible, select:focus-visible { outline: 2px solid #34d399; outline-offset: 3px; }
  select { width: 100%; padding: 0.25rem; border: 1px solid rgb(var(--slate-600)); border-radius: 4px; background: rgb(var(--slate-800)); color: rgb(var(--slate-200)); font-size: 0.75rem; }
  select:disabled { opacity: 0.4; }
</style>
