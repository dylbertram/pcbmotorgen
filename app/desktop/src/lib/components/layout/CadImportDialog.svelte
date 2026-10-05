<script lang="ts">
  import { confirm } from "@tauri-apps/plugin-dialog";
  import { importCadDxf, pickCadDxfPath } from "../../ipc";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { ProjectStore } from "../../stores/project.svelte";
  import type { CadImportResult } from "../../types";
  import { attachBackdropScrollGuard, lockPageScroll } from "../../utils/pageScrollLock";
  import CoilPreviewControls from "../design/CoilPreviewControls.svelte";
  import LayerVisibilityControls from "../design/LayerVisibilityControls.svelte";
  import { CoilPreviewViewState } from "../design/coilPreviewViewState.svelte";
  import {
    formatZoom,
    nextZoomStepDown,
    nextZoomStepUp,
  } from "../../utils/coilPreviewGestures.svelte";

  let {
    config,
    projects,
    onClose,
    onComplete,
  }: {
    config: ConfigStore;
    projects: ProjectStore;
    onClose: () => void;
    onComplete: () => void;
  } = $props();

  let unitsToMm = $state("1");
  let zTolerance = $state(0.05);
  let traceWidthOverride = $state<number | null>(null);
  let traceWidth = $derived(traceWidthOverride ?? config.min_trace_mm);
  let selectedLayersOverride = $state<number | null>(null);
  let selectedLayers = $derived(selectedLayersOverride ?? config.num_layers);
  let selectedPath = $state<string | null>(null);
  let imported = $state<CadImportResult | null>(null);
  let importedOptions = $state("");
  let previewZoom = $state(1);
  const previewView = new CoilPreviewViewState();
  const minZoom = 0.5;
  const maxZoom = 10;
  const zoomSteps = [0.5, 1, 1.5, 2, 3, 4, 6, 8, 10] as const;
  let error = $state<string | null>(null);
  let importFailed = $state(false);
  let busy = $state(false);
  let backdropRef = $state<HTMLDivElement | undefined>(undefined);
  let dialogRef = $state<HTMLDivElement | undefined>(undefined);

  let optionsKey = $derived(
    [unitsToMm, zTolerance, traceWidth, selectedLayers, config.pcb_thickness_mm].join("|"),
  );
  let previewIsCurrent = $derived(Boolean(imported && importedOptions === optionsKey));
  let previewBox = $derived.by(() => {
    const geometry = imported?.geometry;
    if (!geometry) return "0 0 1 1";
    const points = [
      ...geometry.routing.segments.flatMap(({ start, end }) => [start, end]),
      ...geometry.routing.curves.flatMap(({ start, mid, end }) => [start, mid, end]),
      ...geometry.routing.vias.map(({ position }) => position),
    ];
    if (points.length === 0) return "0 0 1 1";

    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const { x, y } of points) {
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
    }
    const span = Math.max(maxX - minX, maxY - minY, geometry.trace_width_mm * 4, 1);
    const padding = Math.max(span * 0.05, geometry.trace_width_mm * 2);
    return `${minX - padding} ${minY - padding} ${Math.max(maxX - minX, 1) + padding * 2} ${Math.max(maxY - minY, 1) + padding * 2}`;
  });
  let previewStrokeWidth = $derived.by(() => {
    const geometry = imported?.geometry;
    if (!geometry) return 1;
    const [, , width, height] = previewBox.split(" ").map(Number);
    return Math.max(geometry.trace_width_mm, Math.max(width, height) / 350);
  });
  let zoomedPreviewBox = $derived.by(() => {
    const [x, y, width, height] = previewBox.split(" ").map(Number);
    const zoomedWidth = width / previewZoom;
    const zoomedHeight = height / previewZoom;
    return `${x + (width - zoomedWidth) / 2} ${y + (height - zoomedHeight) / 2} ${zoomedWidth} ${zoomedHeight}`;
  });
  let previewLayers = $derived(
    imported?.geometry.layer_z_mm.map((_, idx) => ({ idx })) ?? [],
  );

  $effect(() => {
    if (!backdropRef || !dialogRef) return;
    const detachGuard = attachBackdropScrollGuard(backdropRef, dialogRef);
    const unlock = lockPageScroll(document);
    dialogRef.focus();
    return () => {
      detachGuard();
      unlock();
    };
  });

  function baseName(path: string): string {
    return path.slice(Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\")) + 1);
  }

  async function readPreview(path: string): Promise<void> {
    imported = null;
    importedOptions = "";
    previewZoom = 1;
    previewView.layerVisibility = {};
    error = null;
    importFailed = false;
    try {
      imported = await importCadDxf(
        path,
        Number(unitsToMm),
        zTolerance,
        traceWidth,
        selectedLayers,
        config.pcb_thickness_mm,
      );
      importedOptions = optionsKey;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      importFailed = true;
    }
  }

  async function chooseCadFile(): Promise<void> {
    if (busy) return;
    busy = true;
    error = null;
    importFailed = false;
    try {
      const path = await pickCadDxfPath();
      if (!path) return;
      selectedPath = path;
      await readPreview(path);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }

  async function refreshPreview(): Promise<void> {
    if (busy || !selectedPath) return;
    busy = true;
    try {
      await readPreview(selectedPath);
    } finally {
      busy = false;
    }
  }

  async function useImportedGeometry(): Promise<void> {
    if (!imported || !previewIsCurrent || busy) return;
    if (projects.cadGeometry) {
      const replace = await confirm(
        "Replace the currently imported CAD geometry? The project copy is preserved only if you save it first.",
        { title: "Replace custom geometry", kind: "warning", okLabel: "Replace", cancelLabel: "Keep current" },
      );
      if (!replace) return;
    }
    config.num_layers = imported.geometry.layer_z_mm.length;
    projects.setCadGeometry(imported.geometry);
    if (imported.warnings.length > 0) {
      projects.notice = `Imported ${baseName(selectedPath ?? "CAD file")} with ${imported.warnings.length} warning(s). Review the CAD import diagnostics in Design.`;
    }
    onComplete();
  }

  async function useGeneratedGeometry(): Promise<void> {
    const useGenerated = await confirm(
      "Discard the active imported geometry and return to geometry generated from the design settings?",
      { title: "Use generated geometry", kind: "warning", okLabel: "Use generated", cancelLabel: "Keep import" },
    );
    if (!useGenerated) return;
    projects.setCadGeometry(null);
    onComplete();
  }
</script>

<div
  bind:this={backdropRef}
  class="fixed inset-0 z-[120] flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
  role="presentation"
>
  <div
    bind:this={dialogRef}
    class="flex max-h-[min(760px,calc(100dvh-2rem))] w-full max-w-4xl flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-2xl shadow-black/50"
    role="dialog"
    aria-modal="true"
    aria-labelledby="cad-import-title"
    tabindex="-1"
  >
    <header class="shrink-0 border-b border-slate-800 px-5 py-4 md:px-7">
      <p class="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">File · Import</p>
      <h2 id="cad-import-title" class="mt-1 text-lg font-semibold text-slate-100">Import CAD</h2>
      <p class="mt-1 text-xs text-slate-400">Set import options, inspect the geometry preview, then open it in the design.</p>
    </header>

    <div class="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-5 py-4 md:px-7">
      <section class="rounded-md border border-slate-700 bg-slate-950/50 p-4" aria-label="CAD import options">
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label class="text-xs font-medium text-slate-300" for="cad-units">
            DXF units
            <select id="cad-units" aria-label="DXF units" bind:value={unitsToMm} disabled={busy} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 disabled:opacity-50">
              <option value="1">Millimetres</option>
              <option value="25.4">Inches</option>
            </select>
          </label>
          <label class="text-xs font-medium text-slate-300" for="cad-z-tolerance">
            Z tolerance (mm)
            <input id="cad-z-tolerance" aria-label="Z tolerance (mm)" type="number" min="0" step="0.01" bind:value={zTolerance} disabled={busy} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 disabled:opacity-50" />
          </label>
          <label class="text-xs font-medium text-slate-300" for="cad-trace-width">
            Default trace width (mm)
            <input id="cad-trace-width" aria-label="Default trace width (mm)" type="number" min="0.001" step="0.01" value={traceWidth} oninput={(event) => (traceWidthOverride = Number.isFinite(event.currentTarget.valueAsNumber) ? event.currentTarget.valueAsNumber : null)} disabled={busy} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 disabled:opacity-50" />
          </label>
          <div class="flex items-end">
            <p class="pb-2 text-[11px] leading-relaxed text-slate-500">3D layer positions are detected from Z heights.</p>
          </div>
        </div>
      </section>

      {#if error}
        <p role="alert" class="rounded-md border border-rose-500/50 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">{error}</p>
      {/if}

      {#if selectedPath && importFailed && error && !imported}
        <label class="block max-w-xs text-xs font-medium text-slate-300" for="cad-retry-layer-count">
          Copper layers for retry
          <select id="cad-retry-layer-count" value={String(selectedLayers)} onchange={(event) => (selectedLayersOverride = Number(event.currentTarget.value))} disabled={busy} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 disabled:opacity-50">
            {#each config.layerOptions as layer (layer)}<option value={layer}>{layer} layers</option>{/each}
          </select>
        </label>
      {/if}

      {#if imported}
        <section class="space-y-3" aria-label="CAD import preview">
          <div class="flex flex-wrap items-baseline justify-between gap-2">
            <h3 class="text-sm font-medium text-slate-100">Preview · {baseName(selectedPath ?? "CAD file")}</h3>
            <span class="text-[11px] text-slate-400">{imported.geometry.layer_z_mm.length} copper layer(s)</span>
          </div>
          <div class="overflow-hidden rounded-md border border-slate-700 bg-slate-950 p-2">
            <svg
              viewBox={zoomedPreviewBox}
              role="img"
              aria-label="Preview of imported CAD traces and vias"
              preserveAspectRatio="xMidYMid meet"
              class="h-56 w-full"
            >
              {#each imported.geometry.layer_z_mm as _, layer (layer)}
                {#if previewView.isLayerVisible(layer)}
                  <g fill="none" stroke={['#34d399', '#38bdf8', '#c084fc', '#fbbf24', '#fb7185', '#a3e635'][layer % 6]} stroke-width={previewStrokeWidth} stroke-linecap="round" stroke-linejoin="round">
                    {#each imported.geometry.routing.segments.filter((segment) => segment.layer === layer) as segment (segment)}
                      <path d={`M ${segment.start.x} ${segment.start.y} L ${segment.end.x} ${segment.end.y}`} />
                    {/each}
                    {#each imported.geometry.routing.curves.filter((curve) => curve.layer === layer) as curve (curve)}
                      <path d={`M ${curve.start.x} ${curve.start.y} Q ${curve.mid.x} ${curve.mid.y} ${curve.end.x} ${curve.end.y}`} />
                    {/each}
                  </g>
                {/if}
              {/each}
              <g fill="#f8fafc" stroke="#0f172a" stroke-width={previewStrokeWidth * 0.6}>
                {#each imported.geometry.routing.vias as via (via)}
                  <circle cx={via.position.x} cy={via.position.y} r={previewStrokeWidth * 1.8} />
                {/each}
              </g>
            </svg>
          </div>
          <div class="flex flex-wrap items-center justify-between gap-3">
            <LayerVisibilityControls
              layers={previewLayers}
              isVisible={(layerIdx) => previewView.isLayerVisible(layerIdx)}
              onToggle={(layerIdx) => previewView.toggleLayer(layerIdx)}
            />
            <CoilPreviewControls
              zoomLabel={formatZoom(previewZoom)}
              canZoomIn={previewZoom >= maxZoom}
              canZoomOut={previewZoom <= minZoom}
              onZoomIn={() => (previewZoom = nextZoomStepUp(previewZoom, zoomSteps, maxZoom))}
              onZoomOut={() => (previewZoom = nextZoomStepDown(previewZoom, zoomSteps, minZoom))}
              onResetZoom={() => (previewZoom = 1)}
              onResetView={() => (previewZoom = 1)}
            />
          </div>
          <p class="text-xs text-slate-300">
            {imported.geometry.routing.segments.length} line(s),
            {imported.geometry.routing.curves.length} arc(s),
            {imported.geometry.routing.vias.length} via(s).
            Review the preview, then open the design with this geometry.
          </p>
          {#if !previewIsCurrent}
            <p role="status" class="text-xs text-amber-200">Import options changed. Update the preview before opening.</p>
          {/if}
          {#if imported.warnings.length > 0}
            <div class="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
              <p>{imported.warnings.length} import warning(s)</p>
              <ul class="mt-1 list-inside list-disc text-[11px] text-amber-200/80">
                {#each imported.warnings.slice(0, 3) as warning (warning)}<li>{warning}</li>{/each}
              </ul>
            </div>
          {/if}
        </section>
      {:else if !busy && !error}
        <div class="rounded-md border border-dashed border-slate-700 bg-slate-950/30 px-5 py-10 text-center">
          <p class="text-sm font-medium text-slate-200">Choose a DXF file to preview</p>
          <p class="mt-1 text-xs text-slate-500">The current design geometry stays unchanged until you confirm the preview.</p>
        </div>
      {:else if busy}
        <p class="rounded-md border border-slate-700 bg-slate-950/50 px-4 py-5 text-sm text-slate-400">Importing and preparing preview…</p>
      {/if}
    </div>

    <footer class="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-slate-800 px-5 py-3 md:px-7">
      <div class="flex flex-wrap gap-2">
        <button type="button" onclick={onClose} disabled={busy} class="rounded-md px-3 py-2 text-xs text-slate-400 hover:bg-slate-800 hover:text-slate-100 disabled:opacity-50">Cancel</button>
        {#if projects.cadGeometry}
          <button type="button" onclick={useGeneratedGeometry} disabled={busy} class="rounded-md border border-amber-500/40 px-3 py-2 text-xs text-amber-200 hover:bg-amber-500/10 disabled:opacity-50">Use generated geometry</button>
        {/if}
      </div>
      <div class="flex flex-wrap justify-end gap-2">
        {#if imported && previewIsCurrent}
          <button type="button" onclick={chooseCadFile} disabled={busy} class="rounded-md border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50">Choose another file…</button>
          <button type="button" onclick={useImportedGeometry} disabled={busy} class="rounded-md border border-emerald-500/50 bg-emerald-600/30 px-4 py-2 text-xs font-medium text-emerald-100 hover:bg-emerald-500/40 disabled:opacity-50">Open with this geometry</button>
        {:else if imported}
          <button type="button" onclick={refreshPreview} disabled={busy} class="rounded-md border border-sky-500/50 bg-sky-600/30 px-4 py-2 text-xs font-medium text-sky-100 hover:bg-sky-500/40 disabled:opacity-50">{busy ? "Updating…" : "Update preview"}</button>
        {:else if selectedPath && importFailed && error}
          <button type="button" onclick={refreshPreview} disabled={busy} class="rounded-md border border-sky-500/50 bg-sky-600/30 px-4 py-2 text-xs font-medium text-sky-100 hover:bg-sky-500/40 disabled:opacity-50">{busy ? "Retrying…" : "Retry import"}</button>
          <button type="button" onclick={chooseCadFile} disabled={busy} class="rounded-md border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50">Choose another file…</button>
        {:else}
          <button type="button" onclick={chooseCadFile} disabled={busy} class="rounded-md border border-sky-500/50 bg-sky-600/30 px-4 py-2 text-xs font-medium text-sky-100 hover:bg-sky-500/40 disabled:opacity-50">{busy ? "Preparing preview…" : "Choose DXF…"}</button>
        {/if}
      </div>
    </footer>
  </div>
</div>
