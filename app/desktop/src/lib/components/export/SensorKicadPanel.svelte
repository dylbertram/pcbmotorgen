<script lang="ts">
  import { connectKicad, writeSensorToBoard } from "../../ipc";
  import type { SensorStore } from "../../stores/sensor.svelte";
  import type { KicadConnection, KicadWriteResult } from "../../types";

  let { sensor }: { sensor: SensorStore } = $props();
  let connection = $state<KicadConnection | null>(null);
  let result = $state<KicadWriteResult | null>(null);
  let busy = $state(false);
  let dryRun = $state(false);
  let error = $state<string | null>(null);

  async function connect(): Promise<void> {
    busy = true;
    error = null;
    try {
      connection = await connectKicad();
      if (!connection.connected) error = "Open a board in KiCad and enable its IPC API, then connect again.";
    } catch (e) { error = e instanceof Error ? e.message : String(e); }
    finally { busy = false; }
  }

  async function write(): Promise<void> {
    busy = true;
    result = null;
    error = null;
    try {
      result = await writeSensorToBoard(sensor.toIpc(), dryRun);
      if (result.items_attempted === 0) error = "The sensor generated no items. Check the sensor settings before writing.";
    } catch (e) { error = e instanceof Error ? e.message : String(e); }
    finally { busy = false; }
  }
</script>

<section class="space-y-4" aria-label="Sensor KiCad export">
  <p class="text-sm text-slate-300">Write the active sensor file's generated tracks and vias. Motor settings are not used.</p>
  <div class="flex items-center justify-between gap-3 rounded-md border border-slate-700 p-3">
    <p class="text-xs text-slate-400">{connection?.connected ? connection.board_name : "No KiCad board connected"}</p>
    <button type="button" disabled={busy} onclick={() => void connect()} class="rounded-md border border-slate-600 px-3 py-2 text-xs hover:bg-slate-800 focus-visible:outline focus-visible:outline-emerald-400 disabled:opacity-50">Connect</button>
  </div>
  <label class="flex items-center gap-2 text-xs text-slate-300"><input type="checkbox" bind:checked={dryRun} disabled={busy} />Dry run without changing the board</label>
  <button type="button" disabled={busy || sensor.loading || !!sensor.error || (!connection?.connected && !dryRun)} onclick={() => void write()} class="rounded-md bg-emerald-600 px-4 py-2 text-sm hover:bg-emerald-500 focus-visible:outline focus-visible:outline-emerald-300 disabled:opacity-50">{busy ? "Working…" : dryRun ? "Preview sensor write" : "Write tracks and vias"}</button>
  {#if error}<p role="alert" class="text-sm text-rose-300">{error}</p>{/if}
  {#if result && !error}<p role="status" class="text-sm text-emerald-300">{dryRun ? "Dry run" : "Write complete"}: {result.items_created} of {result.items_attempted} items.</p>{/if}
</section>
