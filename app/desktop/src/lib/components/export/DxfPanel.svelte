<script lang="ts">
  import { exportCadGeometryDxf, exportCoilsDxf } from "../../ipc";
  import { saveTextToFile } from "../../files";
  import { pluralize } from "../../format";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { ProjectStore } from "../../stores/project.svelte";
  import type { DxfExportResult } from "../../types";

  let { config, projects }: { config: ConfigStore; projects: ProjectStore } = $props();

  // --- State -------------------------------------------------------------
  let generating = $state(false);
  let error = $state<string | null>(null);
  let result = $state<DxfExportResult | null>(null);
  let saving = $state(false);
  let saveError = $state<string | null>(null);
  let savedTo = $state<string | null>(null);

  // --- Derived -----------------------------------------------------------
  let summaryText = $derived.by(() => {
    const s = result?.summary;
    if (!s) return "";
    return (
      `${pluralize(s.total_lines, "line")} · ` +
      `${pluralize(s.total_arcs, "arc")} · ` +
      `${pluralize(s.total_circles, "circle")} · ` +
      `${pluralize(s.layer_count, "layer")}`
    );
  });

  // --- Handlers ----------------------------------------------------------
  async function handleGenerate(): Promise<void> {
    generating = true;
    error = null;
    result = null;
    savedTo = null;
    try {
      result = projects.cadGeometry
        ? await exportCadGeometryDxf(projects.cadGeometry)
        : await exportCoilsDxf(config.toIpc());
    } catch (e) {
      result = null;
      error = e instanceof Error ? e.message : String(e);
    } finally {
      generating = false;
    }
  }

  async function handleSave(): Promise<void> {
    if (!result) return;
    saving = true;
    saveError = null;
    savedTo = null;
    try {
      const path = await saveTextToFile(result.dxf_content, "coils.dxf", ["dxf"]);
      if (path) savedTo = path;
    } catch (e) {
      saveError = e instanceof Error ? e.message : String(e);
    } finally {
      saving = false;
    }
  }
</script>

<div class="rounded-lg bg-slate-800/40 border border-slate-700 p-4 space-y-3">
  <!-- Error banner -->
  {#if error || saveError}
    <div
      class="rounded-md border border-rose-500/60 bg-rose-500/10 px-3 py-2 text-xs text-rose-200"
      role="alert"
      aria-live="assertive"
    >
      <span class="font-semibold">Error:</span> {error ?? saveError}
    </div>
  {/if}

  <!-- Header row -->
  <div class="flex items-center justify-between gap-3">
    <h3 class="text-sm font-semibold text-slate-200 border-b border-slate-700 pb-1 flex-1">
      DXF export
    </h3>
    {#if result}
      <div class="text-xs text-slate-400 font-mono text-right flex-shrink-0">
        {summaryText}
      </div>
    {:else}
      <div class="text-xs text-slate-500 text-right flex-shrink-0">
        {projects.cadGeometry ? "Export the active imported geometry as 3D DXF." : "Export generated trace geometry as 3D DXF."}
      </div>
    {/if}
  </div>

  <!-- Action buttons -->
  <div class="flex flex-wrap items-center gap-2">
    <button
      type="button"
      onclick={handleGenerate}
      disabled={generating}
      class="rounded-md border border-sky-500/50 bg-sky-600/30 px-3 py-1.5 text-xs font-medium text-sky-100 transition hover:bg-sky-500/40 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {generating ? "Preparing…" : "Prepare 3D DXF"}
    </button>

    {#if result}
      <button
        type="button"
        onclick={handleSave}
        disabled={saving}
        class="rounded-md border border-emerald-500/50 bg-emerald-600/30 px-3 py-1.5 text-xs font-medium text-emerald-100 transition hover:bg-emerald-500/40 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {saving ? "Saving…" : "Save DXF file…"}
      </button>
    {/if}
  </div>

  <!-- Generating indicator -->
  {#if generating}
    <div
      class="rounded-md border border-sky-500/40 bg-sky-500/5 px-3 py-2 text-xs text-sky-200"
      role="status"
      aria-live="polite"
    >
      Preparing a DXF from the active geometry…
    </div>
  {/if}

  <!-- Summary card -->
  {#if result}
    <div
      class="rounded-md border border-emerald-500/50 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200"
      role="status"
      aria-live="polite"
    >
      <div class="font-semibold mb-2">DXF generated</div>
      <div class="grid grid-cols-2 gap-2">
        <div class="rounded border border-slate-700 bg-slate-900/40 px-2 py-1.5">
          <div class="font-mono text-[11px] text-slate-400">lines</div>
          <div class="font-mono text-sm text-slate-100">
            {result.summary.total_lines}
          </div>
        </div>
        <div class="rounded border border-slate-700 bg-slate-900/40 px-2 py-1.5">
          <div class="font-mono text-[11px] text-slate-400">arcs</div>
          <div class="font-mono text-sm text-slate-100">
            {result.summary.total_arcs}
          </div>
        </div>
        <div class="rounded border border-slate-700 bg-slate-900/40 px-2 py-1.5">
          <div class="font-mono text-[11px] text-slate-400">circles</div>
          <div class="font-mono text-sm text-slate-100">
            {result.summary.total_circles}
          </div>
        </div>
        <div class="rounded border border-slate-700 bg-slate-900/40 px-2 py-1.5">
          <div class="font-mono text-[11px] text-slate-400">layers</div>
          <div class="font-mono text-sm text-slate-100">
            {result.summary.layer_count}
          </div>
        </div>
      </div>
    </div>
  {/if}

  <!-- Save confirmation -->
  {#if savedTo}
    <div
      class="rounded-md border border-emerald-500/50 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200"
      role="status"
      aria-live="polite"
    >
      Saved: <span class="font-mono">{savedTo}</span>
    </div>
  {/if}
</div>
