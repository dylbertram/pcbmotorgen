<script lang="ts">
  import { PHASE_COLORS } from "./coilPreviewCanvas";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";

  let { view, uniquePhases, uniqueLayers, hasPolePitchData, hasBandWidthData,
    hasPoleRegionData, poleRegionPhases }: {
    view: CoilPreviewViewState;
    uniquePhases: { idx: number; name: string; colorIdx: number }[];
    uniqueLayers: { idx: number }[];
    hasPolePitchData: boolean;
    hasBandWidthData: boolean;
    hasPoleRegionData: boolean;
    poleRegionPhases: string[];
  } = $props();
</script>

<div class="layer-controls">
  <fieldset class="display-mode">
    <legend>Display</legend>
    <div class="mode-options">
      <label><input type="radio" name="coil-display" value="traces" bind:group={view.traceMode} />Traces</label>
      <label><input type="radio" name="coil-display" value="centerlines" bind:group={view.traceMode} />Centerlines</label>
    </div>
    <label class="layer-row" class:hidden-row={!view.showWaveform} title="Show or hide the phase holding-force waves below the mover slider.">
      <input type="checkbox" bind:checked={view.showWaveform} aria-label="Show phase waveform" />
      <span class="col-span-2">Phase waveform</span>
    </label>
  </fieldset>

  {#if uniqueLayers.length > 0}
    <fieldset>
      <legend>Copper layers</legend>
      {#each uniqueLayers as layer (layer.idx)}
        <label class="layer-row" class:hidden-row={!view.isLayerVisible(layer.idx)}>
          <input type="checkbox" checked={view.isLayerVisible(layer.idx)} onchange={() => view.toggleLayer(layer.idx)} aria-label={"Show layer " + layer.idx} />
          <span class="swatch copper"></span><span>Layer {layer.idx}</span>
        </label>
      {/each}
    </fieldset>
  {/if}

  {#if uniquePhases.length > 0}
    <fieldset aria-label="Phase visibility">
      <legend>Phases</legend>
      {#each uniquePhases as ph (ph.idx)}
        <label class="layer-row" class:hidden-row={!view.isPhaseVisible(ph.idx)}>
          <input type="checkbox" checked={view.isPhaseVisible(ph.idx)} onchange={() => view.phaseVisibility[ph.idx] = !view.isPhaseVisible(ph.idx)} aria-label={"Show phase " + ph.name} />
          <span class="swatch" style:background-color={PHASE_COLORS[ph.colorIdx % PHASE_COLORS.length]}></span>
          <span>Phase {ph.name}</span>
        </label>
      {/each}
    </fieldset>
  {/if}

  <fieldset>
    <legend>Overlays</legend>
    <label class="layer-row" class:hidden-row={!view.showVias}>
      <input type="checkbox" bind:checked={view.showVias} aria-label="Show vias" />
      <span class="swatch" style:background-color="#fbbf24"></span><span>Vias</span>
    </label>
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
      <select aria-label="Pole regions phase" bind:value={view.poleRegionPhase} disabled={!view.showPoleRegions}>
        <option value="">All phases</option>
        {#each poleRegionPhases as phase (phase)}<option value={phase}>{phase}</option>{/each}
      </select>
    {/if}
  </fieldset>

  <fieldset>
    <legend>Pattern</legend>
    <label class="layer-row">
      <input type="checkbox" bind:checked={view.oneSection} aria-label="Show only one repeating section of the pattern" />
      <span class="col-span-2">One electrical period</span>
    </label>
  </fieldset>
</div>

<style>
  .layer-controls { display: grid; gap: 1rem; }
  fieldset { min-width: 0; }
  legend { width: 100%; margin-bottom: 0.35rem; font-size: 0.75rem; font-weight: 600; color: rgb(var(--slate-400)); }
  .layer-row { display: grid; grid-template-columns: 1rem 0.75rem 1fr; align-items: center; gap: 0.6rem; min-height: 2rem; padding: 0.25rem 0.5rem; border-bottom: 1px solid rgb(var(--slate-700)); font-size: 0.75rem; color: rgb(var(--slate-200)); cursor: pointer; }
  .layer-row:hover { background: rgb(var(--slate-800)); }
  .hidden-row { color: rgb(var(--slate-500)); }
  .hidden-row .swatch { opacity: 0.35; }
  .swatch { width: 0.65rem; height: 0.65rem; border-radius: 2px; }
  .copper { background: rgb(var(--slate-300)); }
  .regions { background: linear-gradient(90deg, #f87171 50%, #60a5fa 50%); }
  input { accent-color: #34d399; }
  input:focus-visible, select:focus-visible { outline: 2px solid #34d399; outline-offset: 3px; }
  .mode-options { display: flex; gap: 0.75rem; font-size: 0.75rem; color: rgb(var(--slate-200)); }
  .mode-options label { display: flex; align-items: center; gap: 0.35rem; cursor: pointer; }
  select { width: calc(100% - 2rem); margin: 0.5rem 0 0 2rem; padding: 0.25rem; border: 1px solid rgb(var(--slate-600)); border-radius: 4px; background: rgb(var(--slate-800)); color: rgb(var(--slate-200)); font-size: 0.75rem; }
  select:disabled { opacity: 0.4; }
</style>
