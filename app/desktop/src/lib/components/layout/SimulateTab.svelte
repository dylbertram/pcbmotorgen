<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type {
    ForceSweepResult,
    FrictionBudgetDto,
    HeightStackResultDto,
    DriveAnalysis,
  } from "../../types";
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
    cadGeometryActive = false,
  }: {
    config: ConfigStore;
    active: boolean;
    sweep: ForceSweepResult | null;
    friction: FrictionBudgetDto | null;
    height: HeightStackResultDto | null;
    drive: DriveAnalysis | null;
    driveError?: string | null;
    error: string | null;
    cadGeometryActive?: boolean;
  } = $props();
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
    {#if cadGeometryActive}
      <div class="rounded-md border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-xs text-amber-100" role="status">
        Imported CAD geometry is active, but simulation still uses geometry generated from the design settings.
      </div>
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
    <DriverSuitability analysis={drive} error={driveError} />
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
