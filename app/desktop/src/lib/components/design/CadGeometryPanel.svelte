<script lang="ts">
  import { confirm } from "@tauri-apps/plugin-dialog";
  import { importCadDxf, pickCadDxfPath } from "../../ipc";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { ProjectStore } from "../../stores/project.svelte";
  import type { CadImportResult } from "../../types";

  let { config, projects }: { config: ConfigStore; projects: ProjectStore } = $props();
  let units = $state("1");
  let zTolerance = $state(0.05);
  let traceWidthOverride = $state<number | null>(null);
  let traceWidth = $derived(traceWidthOverride ?? config.min_trace_mm);
  let busy = $state(false);
  let error = $state<string | null>(null);
  let lastImport = $state<CadImportResult | null>(null);

  async function handleImport(): Promise<void> {
    if (busy) return;
    if (projects.cadGeometry) {
      const replace = await confirm("Replace the currently imported CAD geometry? The project copy is preserved only if you save it first.", {
        title: "Replace custom geometry", kind: "warning", okLabel: "Replace", cancelLabel: "Keep current",
      });
      if (!replace) return;
    }
    try {
      const path = await pickCadDxfPath();
      if (!path) return;
      busy = true; error = null; lastImport = null;
      const result = await importCadDxf(path, Number(units), zTolerance, traceWidth, config.num_layers, config.pcb_thickness_mm);
      projects.setCadGeometry(result.geometry);
      lastImport = result;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }

  async function useGenerated(): Promise<void> {
    const ok = await confirm("Discard the active imported geometry and return to geometry generated from the design settings?", {
      title: "Use generated geometry", kind: "warning", okLabel: "Use generated", cancelLabel: "Keep import",
    });
    if (ok) { projects.setCadGeometry(null); lastImport = null; }
  }
</script>

<section class="rounded-md border border-slate-700 bg-slate-800/40 px-3 py-2.5" aria-labelledby="geometry-source-heading">
  <div class="flex items-center justify-between gap-2">
    <h2 id="geometry-source-heading" class="text-xs font-semibold uppercase tracking-wider text-slate-200">Trace geometry</h2>
    <span class="text-[10px] uppercase tracking-wider {projects.cadGeometry ? 'text-amber-300' : 'text-emerald-300'}">
      {projects.cadGeometry ? "Imported CAD" : "Generated"}
    </span>
  </div>
  <p class="mt-1 text-xs text-slate-400">Import Rhino-compatible DXF lines, arcs, and lightweight polylines. Copper layers are grouped by Z height; vertical lines become vias.</p>
  <div class="mt-2 grid grid-cols-2 gap-2">
    <label class="text-[11px] text-slate-400">DXF units
      <select bind:value={units} class="mt-1 w-full rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-100">
        <option value="1">Millimetres</option><option value="25.4">Inches</option>
      </select>
    </label>
    <label class="text-[11px] text-slate-400">Z tolerance (mm)
      <input type="number" min="0" step="0.01" bind:value={zTolerance} class="mt-1 w-full rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-100" />
    </label>
    <label class="col-span-2 text-[11px] text-slate-400">Default trace width (mm)
      <input type="number" min="0.001" step="0.01" value={traceWidth} oninput={(event) => (traceWidthOverride = event.currentTarget.valueAsNumber)} class="mt-1 w-full rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-100" />
    </label>
  </div>
  <div class="mt-2 flex flex-wrap gap-2">
    <button type="button" onclick={handleImport} disabled={busy} class="rounded border border-sky-500/50 bg-sky-600/30 px-3 py-1.5 text-xs text-sky-100 disabled:opacity-40">{busy ? "Importing…" : "Import DXF…"}</button>
    {#if projects.cadGeometry}
      <button type="button" onclick={useGenerated} class="rounded border border-amber-500/50 bg-amber-600/20 px-3 py-1.5 text-xs text-amber-100">Use generated geometry</button>
    {/if}
  </div>
  {#if error}<p role="alert" class="mt-2 text-xs text-rose-300">{error}</p>{/if}
  {#if projects.cadGeometry}
    <p class="mt-2 text-xs text-slate-300">{projects.cadGeometry.routing.segments.length} line(s), {projects.cadGeometry.routing.curves.length} arc(s), {projects.cadGeometry.routing.vias.length} via(s), {projects.cadGeometry.layer_z_mm.length} Z layer(s). Geometry is saved with the project.</p>
    <ul class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-400" aria-label="Imported copper layer heights">
      {#each projects.cadGeometry.layer_z_mm as z, index (z)}
        <li>Layer {index} · Z {z.toFixed(3)} mm</li>
      {/each}
    </ul>
  {/if}
  {#if lastImport?.warnings.length}
    <ul class="mt-2 list-disc space-y-1 pl-4 text-[11px] text-amber-200" aria-label="CAD import warnings">
      {#each lastImport.warnings as warning (warning)}<li>{warning}</li>{/each}
    </ul>
  {/if}
  {#if projects.cadGeometry}
    <p class="mt-2 text-[11px] text-amber-200">Imported geometry is preview/export-only in this version; simulation and KiCad writing continue to use generated geometry.</p>
  {/if}
</section>
