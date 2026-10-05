<script lang="ts">
  import { exportSensorDxf, writeSensorToBoard } from "../../ipc";
  import { saveTextToFile } from "../../files";
  import type { SensorStore } from "../../stores/sensor.svelte";
  import type { DxfExportResult, KicadWriteResult } from "../../types";
  import SensorParamField from "../design/SensorParamField.svelte";

  let { store }: { store: SensorStore } = $props();

  let configKey = $derived(JSON.stringify(store.config));
  let boardBusy = $state(false);
  let boardError = $state<string | null>(null);
  let boardResult = $state<KicadWriteResult | null>(null);
  let boardPreviewKey = $state<string | null>(null);
  let dxfBusy = $state(false);
  let dxfError = $state<string | null>(null);
  let dxfResult = $state<DxfExportResult | null>(null);
  let dxfSavedTo = $state<string | null>(null);

  let boardPreviewIsCurrent = $derived(
    boardResult !== null && boardPreviewKey === configKey,
  );
  let totalTracks = $derived(
    store.geometry?.nets.reduce((sum, net) => sum + net.segments.length, 0) ?? 0,
  );
  let totalVias = $derived(
    store.geometry?.nets.reduce((sum, net) => sum + net.vias.length, 0) ?? 0,
  );

  async function previewBoard(): Promise<void> {
    boardBusy = true;
    boardError = null;
    boardResult = null;
    try {
      const request = store.toIpc();
      boardResult = await writeSensorToBoard(request, true);
      boardPreviewKey = JSON.stringify(request);
    } catch (e) {
      boardError = e instanceof Error ? e.message : String(e);
    } finally {
      boardBusy = false;
    }
  }

  async function writeBoard(): Promise<void> {
    if (!boardPreviewIsCurrent) return;
    boardBusy = true;
    boardError = null;
    try {
      boardResult = await writeSensorToBoard(store.toIpc(), false);
      boardPreviewKey = configKey;
    } catch (e) {
      boardError = e instanceof Error ? e.message : String(e);
    } finally {
      boardBusy = false;
    }
  }

  async function prepareDxf(): Promise<void> {
    dxfBusy = true;
    dxfError = null;
    dxfResult = null;
    dxfSavedTo = null;
    try {
      dxfResult = await exportSensorDxf(store.toIpc());
    } catch (e) {
      dxfError = e instanceof Error ? e.message : String(e);
    } finally {
      dxfBusy = false;
    }
  }

  async function saveDxf(): Promise<void> {
    if (!dxfResult) return;
    dxfBusy = true;
    dxfError = null;
    try {
      dxfSavedTo = await saveTextToFile(dxfResult.dxf_content, "induction-sensor.dxf", ["dxf"]);
    } catch (e) {
      dxfError = e instanceof Error ? e.message : String(e);
    } finally {
      dxfBusy = false;
    }
  }
</script>

<div class="space-y-3">
  <header class="rounded-lg border border-slate-700 bg-slate-800/40 p-4">
    <h1 class="text-sm font-semibold text-slate-100">Inductive position sensor</h1>
    <p class="mt-1 max-w-3xl text-xs leading-relaxed text-slate-400">
      Configure a two-layer sine/cosine receiver and optional transmitter. Sensor wavelength and start position are independent of motor travel; changing motor dimensions will not resize this sensor.
    </p>
  </header>

  <section class="rounded-lg border border-slate-700 bg-slate-800/40 p-3" aria-labelledby="sensor-dimensions-heading">
    <h2 id="sensor-dimensions-heading" class="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-200">Sensor dimensions</h2>
    <div class="grid gap-x-4 gap-y-2 sm:grid-cols-2">
      <SensorParamField label="Wavelength λ (mm)" id="sensor-wavelength" value={store.config.lambda_mm} min={1} step={1} onCommit={(v) => store.set("lambda_mm", v)} />
      <SensorParamField label="X start (mm)" id="sensor-x-start" value={store.config.x_start_mm} step={1} onCommit={(v) => store.set("x_start_mm", v)} />
      <SensorParamField label="Amplitude (mm)" id="sensor-amplitude" value={store.config.amplitude_mm} min={0.1} step={0.1} onCommit={(v) => store.set("amplitude_mm", v)} />
      <SensorParamField label="Turns per receiver" id="sensor-turns" value={store.config.turns} min={1} max={8} step={1} integer onCommit={(v) => store.set("turns", v)} />
    </div>
  </section>

  <section class="rounded-lg border border-slate-700 bg-slate-800/40 p-3" aria-labelledby="sensor-rx-heading">
    <h2 id="sensor-rx-heading" class="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-200">Receiver fabrication</h2>
    <div class="grid gap-x-4 gap-y-2 sm:grid-cols-2">
      <SensorParamField label="RX trace width (mm)" id="sensor-rx-width" value={store.config.trace_width_mm} min={0.05} step={0.01} onCommit={(v) => store.set("trace_width_mm", v)} />
      <SensorParamField label="RX trace gap (mm)" id="sensor-rx-gap" value={store.config.trace_gap_mm} min={0} step={0.01} onCommit={(v) => store.set("trace_gap_mm", v)} />
      <SensorParamField label="Minimum clearance (mm)" id="sensor-clearance" value={store.config.min_clearance_mm} min={0} step={0.01} onCommit={(v) => store.set("min_clearance_mm", v)} />
      <SensorParamField label="RX via size (mm)" id="sensor-via-size" value={store.config.via_size_mm} min={0.1} step={0.05} onCommit={(v) => store.set("via_size_mm", v)} />
      <SensorParamField label="Curve sample step (mm)" id="sensor-arc-step" value={store.config.arc_step_mm} min={0.02} step={0.05} onCommit={(v) => store.set("arc_step_mm", v)} />
      <SensorParamField label="Chip lead-in length (mm)" id="sensor-chip-lead" value={store.config.chip_lead_in_mm} min={1} step={1} onCommit={(v) => store.set("chip_lead_in_mm", v)} />
      <SensorParamField label="Bulge apex offset (mm)" id="sensor-bulge-offset" value={store.config.bulge_apex_offset_mm} step={0.1} onCommit={(v) => store.set("bulge_apex_offset_mm", v)} />
    </div>
  </section>

  <section class="rounded-lg border border-slate-700 bg-slate-800/40 p-3" aria-labelledby="sensor-tx-heading">
    <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
      <h2 id="sensor-tx-heading" class="text-xs font-semibold uppercase tracking-wider text-slate-200">Transmitter</h2>
      <label class="inline-flex items-center gap-2 text-xs text-slate-300">
        <input
          type="checkbox"
          checked={store.config.tx_enabled}
          onchange={(event) => store.set("tx_enabled", (event.currentTarget as HTMLInputElement).checked)}
          class="accent-violet-400"
        />
        Generate OSC spiral
      </label>
    </div>
    {#if store.config.tx_enabled}
      <div class="grid gap-x-4 gap-y-2 sm:grid-cols-2">
        <SensorParamField label="RX/TX left gap (mm)" id="sensor-rx-tx-gap" value={store.config.rx_tx_gap_mm} min={0.1} step={0.05} onCommit={(v) => store.set("rx_tx_gap_mm", v)} />
        <SensorParamField label="TX strand pitch (mm)" id="sensor-tx-pitch" value={store.config.tx_strand_pitch_mm} min={0.1} step={0.05} onCommit={(v) => store.set("tx_strand_pitch_mm", v)} />
        <SensorParamField label="TX corner offset (mm)" id="sensor-tx-corner" value={store.config.tx_corner_offset_mm} min={0.1} step={0.1} onCommit={(v) => store.set("tx_corner_offset_mm", v)} />
        <SensorParamField label="TX trace width (mm)" id="sensor-tx-width" value={store.config.tx_trace_width_mm} min={0.05} step={0.01} onCommit={(v) => store.set("tx_trace_width_mm", v)} />
        <SensorParamField label="TX via size (mm)" id="sensor-tx-via-size" value={store.config.tx_via_size_mm} min={0.1} step={0.05} onCommit={(v) => store.set("tx_via_size_mm", v)} />
      </div>
    {:else}
      <p class="text-xs text-slate-500">The receiver pair will be generated without an OSC transmitter.</p>
    {/if}
  </section>

  <section class="space-y-3 rounded-lg border border-slate-700 bg-slate-800/40 p-3" aria-labelledby="sensor-export-heading">
    <div>
      <h2 id="sensor-export-heading" class="text-xs font-semibold uppercase tracking-wider text-slate-200">Preview and export</h2>
      <p class="mt-1 text-xs text-slate-400">
        {#if store.loading}
          Generating the latest geometry…
        {:else if store.geometry}
          {totalTracks} tracks · {totalVias} vias · {store.geometry.terminal_markers.length} terminal markers
        {:else}
          Generate valid sensor geometry to enable export.
        {/if}
      </p>
    </div>

    {#if store.error || boardError || dxfError}
      <div class="rounded-md border border-rose-500/50 bg-rose-500/10 px-3 py-2 text-xs text-rose-200" role="alert">
        {store.error ?? boardError ?? dxfError}
      </div>
    {/if}

    <div class="flex flex-wrap gap-2">
      <button
        type="button"
        onclick={previewBoard}
        disabled={!store.geometry || store.loading || boardBusy}
        class="rounded-md border border-sky-500/50 bg-sky-600/30 px-3 py-1.5 text-xs font-medium text-sky-100 hover:bg-sky-500/40 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {boardBusy ? "Checking…" : "Check 2-layer KiCad board"}
      </button>
      <button
        type="button"
        onclick={writeBoard}
        disabled={!boardPreviewIsCurrent || boardBusy}
        class="rounded-md border border-emerald-500/50 bg-emerald-600/30 px-3 py-1.5 text-xs font-medium text-emerald-100 hover:bg-emerald-500/40 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {boardBusy ? "Writing…" : "Write tracks and vias"}
      </button>
      <button
        type="button"
        onclick={prepareDxf}
        disabled={!store.geometry || store.loading || dxfBusy}
        class="rounded-md border border-violet-500/50 bg-violet-600/30 px-3 py-1.5 text-xs font-medium text-violet-100 hover:bg-violet-500/40 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {dxfBusy ? "Preparing…" : "Prepare 3D DXF"}
      </button>
      {#if dxfResult}
        <button
          type="button"
          onclick={saveDxf}
          disabled={dxfBusy}
          class="rounded-md border border-slate-600 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700 disabled:opacity-40"
        >Save DXF…</button>
      {/if}
    </div>

    {#if boardResult}
      <div class="rounded-md border border-slate-700 bg-slate-900/60 px-3 py-2 text-xs text-slate-300" role="status">
        {#if boardResult.commit_id === "(dry run - no commit)"}
          Board check passed: {boardResult.items_attempted} tracks/vias would be written. Confirm the current geometry to enable writing.
        {:else}
          KiCad accepted {boardResult.items_created} of {boardResult.items_attempted} items · {boardResult.commit_id}.
        {/if}
        {#if boardPreviewKey !== configKey}
          <span class="ml-1 text-amber-300">Configuration changed; check the board again.</span>
        {/if}
        {#if boardResult.failures.length > 0}
          <ul class="mt-1 list-disc pl-4 text-rose-300">
            {#each boardResult.failures.slice(0, 5) as failure (failure)}<li>{failure}</li>{/each}
          </ul>
        {/if}
      </div>
    {/if}
    {#if dxfResult}
      <div class="rounded-md border border-violet-500/40 bg-violet-500/5 px-3 py-2 text-xs text-violet-100" role="status">
        DXF ready: {dxfResult.summary.total_lines} lines · {dxfResult.summary.total_circles} via circles · {dxfResult.summary.layer_count} layers.
        {#if dxfSavedTo}<span class="ml-1 text-emerald-300">Saved to {dxfSavedTo}</span>{/if}
      </div>
    {/if}
    <p class="text-[11px] leading-relaxed text-slate-500">
      Export writes copper tracks and through-vias only. OSC terminal coordinates are shown as markers; no physical KiCad pads or footprints are created.
    </p>
  </section>
</div>
