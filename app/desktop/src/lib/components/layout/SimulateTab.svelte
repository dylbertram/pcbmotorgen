<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type {
    ForceSweepResult,
    FrictionBudgetDto,
    HeightStackResultDto,
    DriveAnalysis,
    CadGeometry,
  } from "../../types";
  import { unmappedCoils } from "../../cadPhases";
  import { cadMappingProblems } from "../../cadMapping";
  import { inferMissingCoilEnds } from "../../cadTerminals";
  import { usesDeltaConnection } from "../../driverConnection";
  import FluxDiagram from "../simulate/FluxDiagram.svelte";
  import ForceSweepPlot from "../simulate/ForceSweepPlot.svelte";
  import MetricsPanel from "../simulate/MetricsPanel.svelte";
  import DrivePanel from "../design/parameters/DrivePanel.svelte";
  import DriveSettingsPanel from "../simulate/DriveSettingsPanel.svelte";
  import DriverSuitability from "../simulate/DriverSuitability.svelte";

  let {
    config,
    active,
    sweep,
    friction,
    height,
    drive,
    driveError = null,
    error,
    cadGeometry = null,
    onConfigureWinding,
    onSelectEnds,
    onUseInferredEnds,
  }: {
    config: ConfigStore;
    active: boolean;
    sweep: ForceSweepResult | null;
    friction: FrictionBudgetDto | null;
    height: HeightStackResultDto | null;
    drive: DriveAnalysis | null;
    driveError?: string | null;
    error: string | null;
    cadGeometry?: CadGeometry | null;
    onConfigureWinding?: () => void;
    /** Open the coil-ends panel for the active copper. */
    onSelectEnds?: () => void;
    onUseInferredEnds?: () => void;
  } = $props();

  let coilEnds = $derived(cadGeometry ? inferMissingCoilEnds(cadGeometry) : null);
</script>

<div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
  <section class="min-w-0 space-y-4" aria-label="Simulation diagrams">
    <div class="rounded-lg border border-slate-700 bg-slate-800/40 px-4 py-3">
      <h2 class="text-sm font-semibold text-slate-100">Performance iteration</h2>
      <p class="mt-1 text-xs text-slate-400">
        Adjust the design, then use these plots and budgets to compare the next iteration.
        Automated adjustment tips are planned for a later iteration.
      </p>
    </div>
    {#if cadGeometry}
      {#if coilEnds && coilEnds.unresolved.length}
        <div class="rounded-md border border-rose-500/60 bg-rose-500/10 px-3 py-2.5 text-xs text-rose-100" role="alert">
          <p class="font-semibold text-rose-200">Coil ends could not be inferred</p>
          <p class="mt-1 text-rose-100/90">
            Select the driver end and opposite end for {coilEnds.unresolved.join(", ")} in the coil preview to continue.
          </p>
          {#if onSelectEnds}
            <button type="button" onclick={onSelectEnds} class="mt-2 rounded border border-rose-400/60 px-2 py-1 font-medium text-rose-100 hover:bg-rose-500/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-rose-300">Select coil ends</button>
          {/if}
        </div>
      {:else if coilEnds && coilEnds.pending.length}
        <div class="rounded-md border border-amber-500/50 bg-amber-500/10 px-3 py-2.5 text-xs text-amber-100" role="status" aria-label="Inferred coil ends">
          <p class="font-semibold">Coil ends inferred</p>
          <p class="mt-1">Use these ends, or review which end connects to the driver in the coil preview.</p>
          <div class="mt-2 flex gap-2">
            {#if onUseInferredEnds}<button type="button" onclick={onUseInferredEnds} class="rounded border border-amber-400/60 px-2 py-1 hover:bg-amber-500/20">Use inferred ends</button>{/if}
            {#if onSelectEnds}<button type="button" onclick={onSelectEnds} class="rounded border border-slate-600 px-2 py-1 hover:bg-slate-800">Review</button>{/if}
          </div>
        </div>
      {:else if cadMappingProblems(cadGeometry, config.phases, config.min_trace_mm).length}
        <div class="rounded-md border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-xs text-amber-100" role="alert">
          <p>Update the imported geometry before simulating.</p>
          <ul>{#each cadMappingProblems(cadGeometry, config.phases, config.min_trace_mm) as problem (problem)}<li>{problem}</li>{/each}</ul>
        </div>
      {:else}
        <p class="text-xs text-slate-400" role="status">Thrust and driver results use the imported copper.</p>
      {/if}
    {/if}
    {#if error}
      <div
        class="rounded-md border border-rose-500/60 bg-rose-500/10 px-4 py-2 text-sm text-rose-200"
        role="alert"
        aria-live="assertive"
      >
        Computation error: {error}
      </div>
    {/if}
    <FluxDiagram {config} {active} />
    <ForceSweepPlot result={sweep} />
    <DriverSuitability analysis={drive} error={driveError} onConfigureWinding={usesDeltaConnection(config.toIpc(), !!cadGeometry && !unmappedCoils(cadGeometry).length) ? onConfigureWinding : undefined} />
  </section>

  <!-- Side column: drive & force targets and the driver settings sit on top
       so they stay visible while iterating; the metrics summary follows. -->
  <aside class="min-w-0 space-y-4">
    <DrivePanel {config} />
    <DriveSettingsPanel {config} />
    <div class="rounded-lg border border-slate-700 bg-slate-800/40 p-4">
      <MetricsPanel
        {config}
        {sweep}
        {friction}
        {height}
      />
    </div>
  </aside>
</div>
