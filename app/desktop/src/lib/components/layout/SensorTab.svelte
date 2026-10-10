<script lang="ts">
  import type { SensorStore } from "../../stores/sensor.svelte";
  import SensorParamField from "../design/SensorParamField.svelte";

  let { store }: { store: SensorStore } = $props();

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
      <SensorParamField label="KiCad spline step (mm)" id="sensor-arc-step" value={store.config.arc_step_mm} min={0.02} step={0.05} onCommit={(v) => store.set("arc_step_mm", v)} />
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
          aria-label="Generate OSC spiral"
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

</div>
