<!--
  ═══════════════════════════════════════════════════════════════════════
  CoilPreviewVisibilityPanel — the show/hide toggle row: per-phase and
  per-layer trace checkboxes, via + one-section + pole-pitch + band-width
  + pole-region toggles, and the pole-region phase picker.

  Extracted verbatim from CoilPreviewLightbox (kata 426r). There is exactly
  ONE instance in the UI: the lightbox hosts ALL interactive presentation
  toggles — the inline collapsed card carries none. All state lives in the
  shared CoilPreviewViewState instance owned by CoilPreview
  (./coilPreviewViewState.svelte.ts) and passed down as a prop; the
  checkbox/select binds mutate its $state fields in place, so a flip here
  immediately repaints the shared schematic in both the inline and modal
  views and survives open/close cycles.

  Conditional rendering (unchanged): the phase and layer groups render only
  when a payload is loaded; the pole-pitch, band-width and pole-region
  clusters render only when the routing-dimensions sidecar ships matching
  data. The phase picker is disabled while pole regions are hidden.
  ═══════════════════════════════════════════════════════════════════════
-->
<script lang="ts">
  import { PHASE_COLORS } from "./coilPreviewCanvas";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import LayerVisibilityControls from "./LayerVisibilityControls.svelte";

  let {
    view,
    uniquePhases,
    uniqueLayers,
    hasPolePitchData,
    hasBandWidthData,
    hasPoleRegionData,
    poleRegionPhases,
  }: {
    view: CoilPreviewViewState;
    uniquePhases: { idx: number; name: string; colorIdx: number }[];
    uniqueLayers: { idx: number }[];
    hasPolePitchData: boolean;
    hasBandWidthData: boolean;
    hasPoleRegionData: boolean;
    poleRegionPhases: string[];
  } = $props();
</script>

<div class="flex items-center gap-3 flex-wrap">
  <!-- Phase visibility toggles (per phase). A coloured dot + label
       for each phase, with a checkbox to show/hide that phase's
       traces. The label and dot dim when the phase is hidden. -->
  {#if uniquePhases.length > 0}
    <div
      class="flex items-center gap-2 flex-wrap"
      role="group"
      aria-label="Phase visibility"
    >
      {#each uniquePhases as ph (ph.idx)}
        <label
          class="flex items-center gap-1 text-xs select-none cursor-pointer"
          class:text-slate-500={!view.isPhaseVisible(ph.idx)}
          class:text-slate-300={view.isPhaseVisible(ph.idx)}
        >
          <input
            type="checkbox"
            bind:checked={view.phaseVisibility[ph.idx]}
            class="accent-emerald-500"
            aria-label={"Show phase " + ph.name}
          />
          <span
            class="inline-block w-2.5 h-2.5 rounded-full"
            style="background-color: {PHASE_COLORS[
              ph.colorIdx % PHASE_COLORS.length
            ]}; opacity: {view.isPhaseVisible(ph.idx) ? 1 : 0.35}"
          ></span>
          <span>Phase {ph.name}</span>
        </label>
      {/each}
    </div>
  {/if}
  <!-- Layer visibility controls are shared with the CAD import preview. -->
  <LayerVisibilityControls
    layers={uniqueLayers}
    isVisible={(layerIdx) => view.isLayerVisible(layerIdx)}
    onToggle={(layerIdx) => view.toggleLayer(layerIdx)}
  />
  <!-- Via visibility toggle -->
  <label
    class="flex items-center gap-1.5 text-xs text-slate-300 select-none cursor-pointer"
  >
    <input
      type="checkbox"
      bind:checked={view.showVias}
      class="accent-emerald-500"
      aria-label="Show vias"
    />
    <span
      class="inline-block w-2.5 h-2.5 rounded-full"
      style="background-color: #fbbf24; opacity: {view.showVias ? 1 : 0.35}"
    ></span>
    <span>Vias</span>
  </label>
  <!-- One-section toggle -->
  <label
    class="flex items-center gap-1.5 text-xs text-slate-300 select-none cursor-pointer"
  >
    <input
      type="checkbox"
      bind:checked={view.oneSection}
      class="accent-emerald-500"
      aria-label="Show only one repeating section of the pattern"
    />
    <span>one electrical period</span>
  </label>
  <!-- Pole-pitch ruler toggle (only when the sidecar ships a pitch). -->
  {#if hasPolePitchData}
    <label
      class="flex items-center gap-1.5 text-xs text-slate-300 select-none cursor-pointer"
    >
      <input
        type="checkbox"
        bind:checked={view.showPolePitch}
        class="accent-emerald-500"
        aria-label="Show pole-pitch dimension ruler"
      />
      <span
        class="inline-block w-2.5 h-2.5 rounded-full"
        style="background-color: #a5b4fc; opacity: {view.showPolePitch
          ? 1
          : 0.35}"
      ></span>
      <span>Pole pitch</span>
    </label>
  {/if}
  <!-- Band-width diagnostics toggle (only visible with matched rows). -->
  {#if hasBandWidthData}
    <label
      class="flex items-center gap-1.5 text-xs text-slate-300 select-none cursor-pointer"
    >
      <input
        type="checkbox"
        bind:checked={view.showBandWidths}
        class="accent-emerald-500"
        aria-label="Show band-width diagnostics"
      />
      <span
        class="inline-block w-2.5 h-2.5 rounded-full"
        style="background-color: #34d399; opacity: {view.showBandWidths
          ? 1
          : 0.35}"
      ></span>
      <span>Conductor band widths</span>
    </label>
  {/if}
  <!-- Pole-region zones toggle + phase picker (only when the routing
       sidecar ships valid region data). The checkbox is independent
       of per-phase trace visibility; the select picks which phase's
       zones to draw. -->
  {#if hasPoleRegionData}
    <div
      class="flex items-center gap-2"
      role="group"
      aria-label="Pole regions overlay"
    >
      <label
        class="flex items-center gap-1.5 text-xs text-slate-300 select-none cursor-pointer"
      >
        <input
          type="checkbox"
          bind:checked={view.showPoleRegions}
          class="accent-rose-500"
          aria-label="Show pole regions"
        />
        <span
          class="inline-block w-2.5 h-2.5 rounded-full"
          style="background: linear-gradient(90deg, #f87171 50%, #60a5fa 50%); opacity: {view.showPoleRegions
            ? 1
            : 0.35}"
        ></span>
        <span>Pole regions</span>
      </label>
      <select
        aria-label="Pole regions phase"
        class="rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-xs text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus:border-emerald-600"
        bind:value={view.poleRegionPhase}
        disabled={!view.showPoleRegions}
      >
        <option value="">All phases</option>
        {#each poleRegionPhases as phase (phase)}
          <option value={phase}>{phase}</option>
        {/each}
      </select>
    </div>
  {/if}
</div>
