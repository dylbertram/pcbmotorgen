<script lang="ts">
  import { onDestroy } from "svelte";
  import { confirm } from "@tauri-apps/plugin-dialog";
  import { importCadDxf, pickCadDxfPath } from "../../ipc";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { ProjectStore } from "../../stores/project.svelte";
  import type { CadImportResult } from "../../types";
  import { joinCadPreviewEndpoints } from "../../cadPreview";
  import { attachBackdropScrollGuard, lockPageScroll } from "../../utils/pageScrollLock";
  import { fitWorldToView, type WorldTransform } from "../../chart";
  import CoilPreviewControls from "../design/CoilPreviewControls.svelte";
  import LayerVisibilityControls from "../design/LayerVisibilityControls.svelte";
  import { PREVIEW_H, PREVIEW_W } from "../design/coilPreviewCanvas";
  import { CoilPreviewViewState } from "../design/coilPreviewViewState.svelte";
  import {
    CoilPreviewGestures,
  } from "../../utils/coilPreviewGestures.svelte";
  import HelpTag from "../ui/HelpTag.svelte";

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
  let zToleranceDraft = $state("0.05");
  let zToleranceParsed = $derived(parseNumberDraft(zToleranceDraft));
  let zTolerance = $derived(zToleranceParsed ?? 0.05);
  let zToleranceValid = $derived(zToleranceParsed !== null && zToleranceParsed >= 0);
  let traceWidthDraft = $state<string | null>(null);
  let traceWidthText = $derived(traceWidthDraft ?? String(config.min_trace_mm));
  let traceWidthParsed = $derived(parseNumberDraft(traceWidthText));
  let traceWidth = $derived(traceWidthParsed ?? config.min_trace_mm);
  let traceWidthValid = $derived(traceWidthParsed !== null && traceWidthParsed > 0);
  let viaDrillDraft = $state<string | null>(null);
  let viaDrillText = $derived(viaDrillDraft ?? String(config.min_via_drill_mm));
  let viaDrillParsed = $derived(parseNumberDraft(viaDrillText));
  let viaDrill = $derived(viaDrillParsed ?? config.min_via_drill_mm);
  let viaAnnularRingDraft = $state<string | null>(null);
  let viaAnnularRingText = $derived(viaAnnularRingDraft ?? String(config.min_via_annular_ring_mm));
  let viaAnnularRingParsed = $derived(parseNumberDraft(viaAnnularRingText));
  let viaAnnularRing = $derived(viaAnnularRingParsed ?? config.min_via_annular_ring_mm);
  let viaPadRadius = $derived(Math.max(0, viaDrill / 2 + viaAnnularRing));
  let viaDrillRadius = $derived(Math.max(0, viaDrill / 2));
  let viaSizingValid = $derived(
    viaDrillParsed !== null && viaDrillParsed > 0 &&
    viaAnnularRingParsed !== null && viaAnnularRingParsed > 0,
  );
  let selectedLayersOverride = $state<number | null>(null);
  let selectedLayers = $derived(selectedLayersOverride ?? config.num_layers);
  let selectedPath = $state<string | null>(null);
  let imported = $state<CadImportResult | null>(null);
  let importedOptions = $state("");
  const previewView = new CoilPreviewViewState();
  const previewPad = 24;
  let error = $state<string | null>(null);
  let importFailed = $state(false);
  let busy = $state(false);
  let refreshScheduled = $state(false);
  let previewFrameRef = $state<HTMLDivElement | undefined>(undefined);
  let backdropRef = $state<HTMLDivElement | undefined>(undefined);
  let dialogRef = $state<HTMLDivElement | undefined>(undefined);
  let previewRefreshTimer: ReturnType<typeof setTimeout> | undefined;

  let optionsKey = $derived(
    [unitsToMm, zTolerance, traceWidth, selectedLayers, config.pcb_thickness_mm].join("|"),
  );
  let importSettingsValid = $derived(zToleranceValid && traceWidthValid);
  let previewIsCurrent = $derived(
    Boolean(imported && importedOptions === optionsKey && importSettingsValid),
  );
  let previewBounds = $derived.by(() => {
    const geometry = imported?.geometry;
    if (!geometry) return { minX: 0, minY: 0, maxX: 1, maxY: 1 };
    const points = [
      ...geometry.routing.segments.flatMap(({ start, end }) => [start, end]),
      ...geometry.routing.curves.flatMap(({ start, mid, end }) => [start, mid, end]),
      ...geometry.routing.vias.map(({ position }) => position),
    ];
    if (points.length === 0) return { minX: 0, minY: 0, maxX: 1, maxY: 1 };

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
    const effectiveTraceWidth = traceWidthValid ? traceWidth : geometry.trace_width_mm;
    const span = Math.max(maxX - minX, maxY - minY, effectiveTraceWidth * 4, 1);
    const padding = Math.max(span * 0.05, effectiveTraceWidth * 2, viaPadRadius * 1.5);
    return {
      minX: minX - padding,
      minY: minY - padding,
      maxX: maxX + padding,
      maxY: maxY + padding,
    };
  });
  let previewStrokeWidth = $derived.by(() => {
    if (traceWidthValid) return traceWidth;
    return imported?.geometry.trace_width_mm ?? config.min_trace_mm;
  });
  let joinedPreview = $derived.by(() =>
    imported
      ? joinCadPreviewEndpoints(imported.geometry, zToleranceValid ? zTolerance : 0)
      : { segments: [], curves: [] },
  );
  function worldTransformFor(zoom: number): WorldTransform {
    return fitWorldToView(previewBounds, PREVIEW_W, PREVIEW_H, previewPad, zoom);
  }
  const gestures = new CoilPreviewGestures({
    virtualW: PREVIEW_W,
    virtualH: PREVIEW_H,
    minZoom: 0.5,
    maxZoom: 10,
    zoomSteps: [0.5, 1, 1.5, 2, 3, 4, 6, 8, 10],
    getWorldTransform: worldTransformFor,
  });
  let worldTransform = $derived(worldTransformFor(gestures.zoom));
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

  $effect(() => {
    const frame = previewFrameRef;
    if (!frame) return;
    frame.addEventListener("wheel", gestures.handleWheel, { passive: false });
    return () => frame.removeEventListener("wheel", gestures.handleWheel);
  });

  onDestroy(() => {
    if (previewRefreshTimer) clearTimeout(previewRefreshTimer);
  });

  function baseName(path: string): string {
    return path.slice(Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\")) + 1);
  }

  function parseNumberDraft(value: string): number | null {
    if (value.trim() === "") return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function schedulePreviewRefresh(): void {
    if (!selectedPath) return;
    if (!importSettingsValid) return;
    if (previewRefreshTimer) clearTimeout(previewRefreshTimer);
    refreshScheduled = true;
    previewRefreshTimer = setTimeout(() => {
      previewRefreshTimer = undefined;
      refreshScheduled = false;
      void refreshPreview();
    }, 350);
  }

  async function readPreview(path: string): Promise<void> {
    const requestedOptions = optionsKey;
    const requestedTraceWidth = traceWidth;
    error = null;
    importFailed = false;
    try {
      const result = await importCadDxf(
        path,
        Number(unitsToMm),
        zTolerance,
        traceWidth,
        selectedLayers,
        config.pcb_thickness_mm,
      );
      if (path === selectedPath && requestedOptions === optionsKey) {
        imported = {
          ...result,
          geometry: { ...result.geometry, trace_width_mm: requestedTraceWidth },
        };
        importedOptions = requestedOptions;
      } else if (path === selectedPath) {
        schedulePreviewRefresh();
      }
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      importFailed = true;
    }
  }

  async function chooseCadFile(): Promise<void> {
    if (busy || !importSettingsValid) return;
    if (previewRefreshTimer) clearTimeout(previewRefreshTimer);
    previewRefreshTimer = undefined;
    refreshScheduled = false;
    busy = true;
    error = null;
    importFailed = false;
    try {
      const path = await pickCadDxfPath();
      if (!path) return;
      selectedPath = path;
      imported = null;
      importedOptions = "";
      gestures.resetView();
      previewView.layerVisibility = {};
      await readPreview(path);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }

  async function refreshPreview(): Promise<void> {
    if (busy || !selectedPath || !importSettingsValid) return;
    busy = true;
    try {
      await readPreview(selectedPath);
    } finally {
      busy = false;
    }
  }

  function updateTraceWidth(event: Event): void {
    const input = event.currentTarget as HTMLInputElement;
    traceWidthDraft = input.value;
    if (traceWidthValid) schedulePreviewRefresh();
  }

  function updateZTolerance(event: Event): void {
    const input = event.currentTarget as HTMLInputElement;
    zToleranceDraft = input.value;
    if (zToleranceValid) schedulePreviewRefresh();
  }

  function updateViaDrill(event: Event): void {
    const input = event.currentTarget as HTMLInputElement;
    viaDrillDraft = input.value;
  }

  function updateViaAnnularRing(event: Event): void {
    const input = event.currentTarget as HTMLInputElement;
    viaAnnularRingDraft = input.value;
  }

  async function useImportedGeometry(): Promise<void> {
    if (!imported || !previewIsCurrent || !viaSizingValid || busy) return;
    if (projects.cadGeometry) {
      const replace = await confirm(
        "Replace the currently imported CAD geometry? The project copy is preserved only if you save it first.",
        { title: "Replace custom geometry", kind: "warning", okLabel: "Replace", cancelLabel: "Keep current" },
      );
      if (!replace) return;
    }
    config.num_layers = imported.geometry.layer_z_mm.length;
    config.min_via_drill_mm = viaDrill;
    config.min_via_annular_ring_mm = viaAnnularRing;
    projects.setCadGeometry(imported.geometry);
    if (imported.warnings.length > 0) {
      projects.notice = `Imported ${baseName(selectedPath ?? "CAD file")} with ${imported.warnings.length} warning(s): ${imported.warnings.slice(0, 3).join(" ")}`;
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
  onclick={(event) => {
    if (event.target === event.currentTarget && !busy) onClose();
  }}
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
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label class="text-xs font-medium text-slate-300" for="cad-units">
            DXF units
            <select id="cad-units" aria-label="DXF units" bind:value={unitsToMm} onchange={schedulePreviewRefresh} disabled={busy} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 disabled:opacity-50">
              <option value="1">Millimetres</option>
              <option value="25.4">Inches</option>
            </select>
          </label>
          <label class="text-xs font-medium text-slate-300" for="cad-z-tolerance">
            <span class="inline-flex items-center">Z tolerance (mm)<HelpTag label="About Z tolerance" tip="Controls how close Z heights must be to count as one copper layer. It also allows small XY offsets when recognizing vertical via centerlines and matching via endpoints to traces. Lower it if nearby layers merge; raise it only to accommodate coordinate noise." /></span>
            <input id="cad-z-tolerance" aria-label="Z tolerance (mm)" type="text" inputmode="decimal" value={zToleranceDraft} oninput={updateZTolerance} disabled={busy} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 disabled:opacity-50" />
          </label>
          <label class="text-xs font-medium text-slate-300" for="cad-trace-width">
            <span class="inline-flex items-center">Trace width (mm)<HelpTag label="About trace width" tip="Applied uniformly to imported trace centerlines. This value controls their preview width and overrides embedded global trace-width metadata." /></span>
            <input id="cad-trace-width" aria-label="Trace width (mm)" type="text" inputmode="decimal" value={traceWidthText} oninput={updateTraceWidth} disabled={busy} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 disabled:opacity-50" />
          </label>
          <label class="text-xs font-medium text-slate-300" for="cad-via-drill">
            Via drill (mm)
            <input id="cad-via-drill" aria-label="Via drill (mm)" type="text" inputmode="decimal" value={viaDrillText} oninput={updateViaDrill} disabled={busy} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 disabled:opacity-50" />
          </label>
          <label class="text-xs font-medium text-slate-300" for="cad-via-annular-ring">
            Via annular ring (mm)
            <input id="cad-via-annular-ring" aria-label="Via annular ring (mm)" type="text" inputmode="decimal" value={viaAnnularRingText} oninput={updateViaAnnularRing} disabled={busy} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 disabled:opacity-50" />
          </label>
          <div class="flex items-end">
            <p class="pb-2 text-[11px] leading-relaxed text-slate-500">3D layer positions are detected from Z heights. Via sizes use the project manufacturing defaults.</p>
          </div>
        </div>
        {#if !importSettingsValid}
          <p role="alert" class="mt-3 text-xs text-rose-200">Enter a positive trace width and a non-negative Z tolerance to import.</p>
        {/if}
      </section>

      {#if error}
        <p role="alert" class="rounded-md border border-rose-500/50 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">{error}</p>
      {/if}

      {#if selectedPath && importFailed && error}
        <label class="block max-w-xs text-xs font-medium text-slate-300" for="cad-retry-layer-count">
          Copper layers for retry
          <select id="cad-retry-layer-count" value={String(selectedLayers)} onchange={(event) => { selectedLayersOverride = Number(event.currentTarget.value); schedulePreviewRefresh(); }} disabled={busy} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 disabled:opacity-50">
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
          <div
            bind:this={previewFrameRef}
            class="relative w-full touch-none select-none overflow-hidden rounded-md border border-slate-700 bg-slate-950 {gestures.isPanning ? 'cursor-grabbing' : 'cursor-grab'}"
            role="img"
            aria-label="CAD import preview"
            style={`aspect-ratio: ${PREVIEW_W} / ${PREVIEW_H}`}
            onpointerdown={gestures.handlePointerDown}
            onpointermove={gestures.handlePointerMove}
            onpointerup={gestures.handlePointerEnd}
            onpointercancel={gestures.handlePointerEnd}
            onlostpointercapture={gestures.handleLostPointerCapture}
            ontouchstart={gestures.handleTouchStart}
            ontouchmove={gestures.handleTouchMove}
            ontouchend={gestures.handleTouchEnd}
            ontouchcancel={gestures.handleTouchEnd}
          >
            <svg
              viewBox={`0 0 ${PREVIEW_W} ${PREVIEW_H}`}
              aria-hidden="true"
              preserveAspectRatio="xMidYMid meet"
              class="block h-full w-full"
            >
              <g transform={`matrix(${worldTransform.s} 0 0 ${-worldTransform.s} ${worldTransform.tx + gestures.panX} ${worldTransform.ty + gestures.panY})`}>
                {#each imported.geometry.layer_z_mm as _, layer (layer)}
                  {#if previewView.isLayerVisible(layer)}
                    <g fill="none" stroke={['#34d399', '#38bdf8', '#c084fc', '#fbbf24', '#fb7185', '#a3e635'][layer % 6]} stroke-width={previewStrokeWidth} stroke-linecap="round" stroke-linejoin="round">
                      {#each joinedPreview.segments.filter((segment) => segment.layer === layer) as segment (segment)}
                        <path d={`M ${segment.start.x} ${segment.start.y} L ${segment.end.x} ${segment.end.y}`} />
                      {/each}
                      {#each joinedPreview.curves.filter((curve) => curve.layer === layer) as curve (curve)}
                        <path d={`M ${curve.start.x} ${curve.start.y} Q ${curve.mid.x} ${curve.mid.y} ${curve.end.x} ${curve.end.y}`} />
                      {/each}
                    </g>
                  {/if}
                {/each}
                <g fill="#fbbf24" stroke="#0f172a" stroke-width={previewStrokeWidth * 0.25}>
                  {#each imported.geometry.routing.vias as via (via)}
                    <circle cx={via.position.x} cy={via.position.y} r={viaPadRadius} />
                  {/each}
                </g>
                <g fill="#020617" stroke="#0f172a" stroke-width={previewStrokeWidth * 0.2}>
                  {#each imported.geometry.routing.vias as via (via)}
                    <circle cx={via.position.x} cy={via.position.y} r={viaDrillRadius} />
                  {/each}
                </g>
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
              zoomLabel={gestures.zoomLabel}
              canZoomIn={gestures.canZoomIn}
              canZoomOut={gestures.canZoomOut}
              onZoomIn={gestures.zoomIn}
              onZoomOut={gestures.zoomOut}
              onResetZoom={gestures.zoomReset}
              onResetView={gestures.resetView}
            />
          </div>
          <p class="text-xs text-slate-300">
            {imported.geometry.routing.segments.length} line(s),
            {imported.geometry.routing.curves.length} arc(s),
            {imported.geometry.routing.vias.length} via(s).
            Drag to pan; pinch or ctrl-scroll to zoom. Review the preview, then open the design with this geometry.
          </p>
          <p class="text-[11px] text-slate-500">
            Nearby endpoints are aligned for display only. Saved and exported geometry keeps the original DXF coordinates.
          </p>
          {#if !viaSizingValid}
            <p role="alert" class="text-xs text-rose-200">Via drill and annular ring must be positive values.</p>
          {/if}
          {#if !previewIsCurrent}
            <p role="status" class="text-xs text-amber-200">{refreshScheduled || busy ? "Updating preview for changed options…" : "Preview settings changed; preview will refresh automatically."}</p>
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
        {#if imported && previewIsCurrent && viaSizingValid}
          <button type="button" onclick={chooseCadFile} disabled={busy} class="rounded-md border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50">Choose another file…</button>
          <button type="button" onclick={useImportedGeometry} disabled={busy} class="rounded-md border border-emerald-500/50 bg-emerald-600/30 px-4 py-2 text-xs font-medium text-emerald-100 hover:bg-emerald-500/40 disabled:opacity-50">Open with this geometry</button>
        {:else if selectedPath && importFailed && error && !refreshScheduled}
          <button type="button" onclick={refreshPreview} disabled={busy || !importSettingsValid} class="rounded-md border border-sky-500/50 bg-sky-600/30 px-4 py-2 text-xs font-medium text-sky-100 hover:bg-sky-500/40 disabled:opacity-50">{busy ? "Retrying…" : "Retry import"}</button>
          <button type="button" onclick={chooseCadFile} disabled={busy} class="rounded-md border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50">Choose another file…</button>
        {:else if selectedPath}
          <span role="status" class="px-3 py-2 text-xs text-slate-400">{busy || refreshScheduled ? "Updating preview…" : "Preview updates automatically when settings change."}</span>
        {:else}
          <button type="button" onclick={chooseCadFile} disabled={busy || !importSettingsValid} class="rounded-md border border-sky-500/50 bg-sky-600/30 px-4 py-2 text-xs font-medium text-sky-100 hover:bg-sky-500/40 disabled:opacity-50">{busy ? "Preparing preview…" : "Choose DXF…"}</button>
        {/if}
      </div>
    </footer>
  </div>
</div>
