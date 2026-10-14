<script lang="ts">
  import { onDestroy, untrack } from "svelte";
  import { confirm } from "@tauri-apps/plugin-dialog";
  import { importCadDxf, pickCadDxfPath } from "../../ipc";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { ProjectStore } from "../../stores/project.svelte";
  import type { SensorStore } from "../../stores/sensor.svelte";
  import type { CadGeometry, CadImportResult } from "../../types";
  import { cadCoilNames, joinCadPreviewEndpoints } from "../../cadPreview";
  import { simplifyCadLines } from "../../cadSimplify";
  import { PHASE_COLORS } from "../design/coilPreviewCanvas";
  import { arcSvgPath, splineSvgPath } from "../../curvePaths";
  import { attachBackdropScrollGuard, lockPageScroll } from "../../utils/pageScrollLock";
  import { fitWorldToView, type WorldTransform } from "../../chart";
  import CoilPreviewControls from "../design/CoilPreviewControls.svelte";
  import PreviewLayersPopover from "../design/PreviewLayersPopover.svelte";
  import PreviewFrame from "../design/PreviewFrame.svelte";
  import GeometryEditingToolbar from "../design/GeometryEditingToolbar.svelte";
  import GeometryEditingOverlay from "../design/GeometryEditingOverlay.svelte";
  import PreviewMeasureOverlay from "../design/PreviewMeasureOverlay.svelte";
  import CoilTerminalPanel from "../design/CoilTerminalPanel.svelte";
  import CoilTerminalSummary from "../design/CoilTerminalSummary.svelte";
  import { CoilTerminalTool } from "../../utils/coilTerminalTool.svelte";
  import { CoilPreviewMeasure } from "../../utils/coilPreviewMeasure.svelte";
  import { CadSimplifyTool } from "../../utils/cadSimplifyTool.svelte";
  import { clientToVirtual, virtualToWorld } from "../../previewGeometry";
  import { PREVIEW_H, PREVIEW_W } from "../design/coilPreviewCanvas";
  import { CoilPreviewViewState } from "../design/coilPreviewViewState.svelte";
  import {
    CoilPreviewGestures,
  } from "../../utils/coilPreviewGestures.svelte";
  import HelpTag from "../ui/HelpTag.svelte";
  import ViaSizingGuide from "../design/ViaSizingGuide.svelte";
  import { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";

  let {
    config,
    projects,
    sensor,
    initialCoilType = "motor",
    onClose,
    onComplete,
  }: {
    config: ConfigStore;
    projects: ProjectStore;
    sensor: SensorStore;
    initialCoilType?: "motor" | "sensor";
    onClose: () => void;
    onComplete: (coilType: "motor" | "sensor") => void;
  } = $props();

  let coilType = $state(untrack(() => initialCoilType));
  let existingGeometry = $derived(coilType === "sensor" ? sensor.cadGeometry : projects.cadGeometry);
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
  let selectedLayers = $derived(selectedLayersOverride ?? (coilType === "sensor" ? 2 : config.num_layers));
  let selectedPath = $state<string | null>(null);
  let imported = $state.raw<CadImportResult | null>(null);
  let edited = $state(false);
  const selection = new CadSelectionTool({
    getGeometry: () => imported?.geometry ?? null,
    onChange: updateImportedGeometry,
    tolerance: () => zTolerance,
  });
  let importedOptions = $state("");
  let simplifyLines = $state(false);
  let sourceLayerCoils = $state<Record<string, string>>({});
  let hiddenCoils = $state<Record<string, boolean>>({});
  let previewCoils = $derived(imported ? cadCoilNames(imported.geometry) : []);
  function coilColor(net: string): string {
    return PHASE_COLORS[previewCoils.indexOf(net) % PHASE_COLORS.length];
  }
  function coilHidden(net: string): boolean {
    return hiddenCoils[net] === true;
  }
  function traceVisible(coil: string, layer: number): boolean {
    return !coilHidden(coil) && previewView.isLayerVisible(layer) && previewView.isCoilLayerVisible(coil, layer);
  }
  const previewView = new CoilPreviewViewState();
  const previewPad = 24;
  let error = $state<string | null>(null);
  let importFailed = $state(false);
  let busy = $state(false);
  let refreshScheduled = $state(false);
  let previewFrameRef = $state<HTMLDivElement | undefined>(undefined);
  let previewWidth = $state(PREVIEW_W);
  let previewHeight = $state(PREVIEW_H);
  let viewportWidth = $derived(Math.max(1, previewWidth));
  let viewportHeight = $derived(Math.max(1, previewHeight));
  let backdropRef = $state<HTMLDivElement | undefined>(undefined);
  let dialogRef = $state<HTMLDivElement | undefined>(undefined);
  let previewRefreshTimer: ReturnType<typeof setTimeout> | undefined;

  let optionsKey = $derived(
    [unitsToMm, zTolerance, traceWidth, selectedLayers, config.pcb_thickness_mm, simplifyLines, JSON.stringify(sourceLayerCoils)].join("|"),
  );
  let importSettingsValid = $derived(zToleranceValid && traceWidthValid && Object.values(sourceLayerCoils).every((coil) => coil.trim() !== ""));
  let previewIsCurrent = $derived(
    Boolean(imported && importedOptions === optionsKey && importSettingsValid),
  );
  let previewBounds = $derived.by(() => {
    const geometry = imported?.geometry;
    if (!geometry) return { minX: 0, minY: 0, maxX: 1, maxY: 1 };
    const points = [
      ...geometry.routing.segments.flatMap(({ start, end }) => [start, end]),
      ...geometry.routing.curves.flatMap(({ start, mid, end }) => [start, mid, end]),
      ...(geometry.routing.splines ?? []).flatMap((spline) => spline.control_points),
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
    return fitWorldToView(previewBounds, viewportWidth, viewportHeight, previewPad, zoom);
  }
  const gestures = new CoilPreviewGestures({
    interactionMode: "cad",
    get virtualW() { return viewportWidth; },
    get virtualH() { return viewportHeight; },
    minZoom: 0.5,
    maxZoom: Infinity,
    zoomSteps: [0.5, 1, 1.5, 2, 3, 4, 6, 8, 10],
    getWorldTransform: worldTransformFor,
  });
  let worldTransform = $derived(worldTransformFor(gestures.zoom));
  let renderedStrokeWidth = $derived(previewView.traceMode === "centerlines" ? 1 / worldTransform.s : previewStrokeWidth);
  const measure = new CoilPreviewMeasure({
    screenToWorld: (x, y) => {
      if (!previewFrameRef) return null;
      const point = clientToVirtual(x, y, previewFrameRef.getBoundingClientRect(), viewportWidth, viewportHeight);
      const world = virtualToWorld(point.x, point.y, worldTransform, gestures.panX, gestures.panY);
      return { x: world.x / 1000, y: world.y / 1000 };
    },
  });
  const terminalTool = new CoilTerminalTool({
    getGeometry: () => imported?.geometry ?? null,
    onChange: updateImportedGeometry,
    onReveal: (coil, layer) => {
      hiddenCoils = { ...hiddenCoils, [coil]: false };
      previewView.layerVisibility = { ...previewView.layerVisibility, [layer]: true };
      previewView.showCoilLayer(coil, layer);
    },
    onFit: gestures.resetView,
  });
  const simplifyTool = new CadSimplifyTool({ getGeometry: () => imported?.geometry ?? null, onChange: updateImportedGeometry });
  function updateImportedGeometry(geometry: CadGeometry): void {
    if (!imported) return;
    imported = { ...imported, geometry };
    edited = true;
  }
  function startTerminals(coil?: string): void {
    selection.setMode("pan");
    measure.mode = false;
    measure.clear();
    terminalTool.begin(coil);
  }
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

  onDestroy(() => {
    terminalTool.cancel();
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
    if (edited) { refreshScheduled = false; return; }
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
        sourceLayerCoils,
      );
      if (path === selectedPath && requestedOptions === optionsKey) {
        imported = {
          ...result,
          geometry: {
            ...(simplifyLines ? simplifyCadLines(result.geometry) : result.geometry),
            trace_width_mm: requestedTraceWidth,
            source_file_name: baseName(path),
          },
        };
        importedOptions = requestedOptions;
        edited = false;
        selection.clear();
        selection.before = null;
        selection.after = null;
        terminalTool.cancel();
        measure.clear();
        simplifyTool.reset();
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
      edited = false;
      imported = null;
      importedOptions = "";
      sourceLayerCoils = {};
      hiddenCoils = {};
      selection.clear();
      selection.before = null;
      selection.after = null;
      gestures.resetView();
      terminalTool.cancel();
      measure.mode = false;
      measure.clear();
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
    if (edited && !await confirm("Reimporting replaces your segment assignments. Reimport with the new settings?", { title: "Replace preview edits", okLabel: "Reimport", cancelLabel: "Keep edits", kind: "warning" })) return;
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

  function assignSourceLayer(name: string, coil: string): void {
    sourceLayerCoils = { ...sourceLayerCoils, [name]: coil };
    schedulePreviewRefresh();
  }

  function updateCoilType(event: Event): void {
    coilType = (event.currentTarget as HTMLSelectElement).value as "motor" | "sensor";
    selectedLayersOverride = null;
    schedulePreviewRefresh();
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
    if (existingGeometry) {
      const replace = await confirm(
        `Replace the currently imported ${coilType === "sensor" ? "sensor" : "motor coil"} CAD geometry? The project copy is preserved only if you save it first.`,
        { title: "Replace custom geometry", kind: "warning", okLabel: "Replace", cancelLabel: "Keep current" },
      );
      if (!replace) return;
    }
    if (coilType === "motor") config.num_layers = imported.geometry.layer_z_mm.length;
    config.min_via_drill_mm = viaDrill;
    config.min_via_annular_ring_mm = viaAnnularRing;
    if (coilType === "sensor") {
      sensor.set("via_size_mm", viaDrill + 2 * viaAnnularRing);
      sensor.cadGeometry = imported.geometry;
    }
    else projects.setCadGeometry(imported.geometry);
    if (imported.warnings.length > 0) {
      projects.notice = `Imported ${baseName(selectedPath ?? "CAD file")} with ${imported.warnings.length} warning(s): ${imported.warnings.slice(0, 3).join(" ")}`;
    }
    onComplete(coilType);
  }

  async function useGeneratedGeometry(): Promise<void> {
    const useGenerated = await confirm(
      "Discard the active imported geometry and return to geometry generated from the design settings?",
      { title: "Use generated geometry", kind: "warning", okLabel: "Use generated", cancelLabel: "Keep import" },
    );
    if (!useGenerated) return;
    if (coilType === "sensor") sensor.cadGeometry = null;
    else projects.setCadGeometry(null);
    onComplete(coilType);
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
    class="flex h-[calc(100dvh-2rem)] max-h-[900px] w-full max-w-7xl flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-2xl shadow-black/50"
    role="dialog"
    aria-modal="true"
    aria-labelledby="cad-import-title"
    tabindex="-1"
    onkeydown={(event) => {
      if (event.key !== "Escape" || busy) return;
      event.preventDefault();
      event.stopPropagation();
      if (terminalTool.active) terminalTool.cancel();
      else if (selection.mode !== "pan") { selection.clear(); selection.setMode("pan"); }
      else if (measure.mode) { measure.mode = false; measure.clear(); }
      else onClose();
    }}
  >
    <header class="flex shrink-0 items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
      <h2 id="cad-import-title" class="text-sm font-semibold text-slate-100">Import CAD</h2>
      <span class="truncate text-xs text-slate-400">{selectedPath ? baseName(selectedPath) : "Choose a DXF file"}</span>
    </header>

    <div class="import-layout min-h-0 flex-1">
      <aside class="import-settings space-y-3 overflow-y-auto overscroll-contain border-r border-slate-700 p-3" aria-label="Import settings">
      <section aria-label="CAD import options">
        <div class="grid grid-cols-2 gap-3">
          <label class="text-xs font-medium text-slate-300" for="cad-coil-type">
            Coil type
            <select id="cad-coil-type" value={coilType} disabled title="Create another file to import a different coil type." class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 disabled:opacity-50">
              <option value="motor">Motor coil</option>
              <option value="sensor">Sensor coil</option>
            </select>
          </label>
          <label class="text-xs font-medium text-slate-300" for="cad-z-tolerance">
            <span class="inline-flex items-center">Z tolerance (mm)<HelpTag label="About Z tolerance" tip="Groups nearby Z heights into copper layers and matches via endpoints. Lower it if separate layers merge." /></span>
            <input id="cad-z-tolerance" aria-label="Z tolerance (mm)" type="text" inputmode="decimal" value={zToleranceDraft} oninput={updateZTolerance} disabled={busy} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 disabled:opacity-50" />
          </label>
          <label class="text-xs font-medium text-slate-300" for="cad-trace-width">
            <span class="inline-flex items-center">Trace width (mm)<HelpTag label="About trace width" tip="Sets the width of all imported traces in previews and exports. Overrides the DXF trace-width metadata." /></span>
            <input id="cad-trace-width" aria-label="Trace width (mm)" type="text" inputmode="decimal" value={traceWidthText} oninput={updateTraceWidth} disabled={busy} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 disabled:opacity-50" />
          </label>
        </div>
        <details class="mt-3 text-xs text-slate-300">
        <summary class="cursor-pointer" title="Set the drilled hole and copper ring sizes for imported vias.">Via sizes</summary>
        <ViaSizingGuide holeMm={viaDrill} ringMm={viaAnnularRing}>
          <label class="flex items-center justify-between gap-2 text-xs font-medium text-slate-300" for="cad-via-drill">
            <span>Via hole size (mm)<HelpTag label="About via hole size" tip="The diameter of the drilled hole, excluding the surrounding copper ring. This is not the outer via diameter." /></span>
            <input id="cad-via-drill" aria-label="Via hole size (mm)" type="text" inputmode="decimal" value={viaDrillText} oninput={updateViaDrill} disabled={busy} class="w-24 shrink-0 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 disabled:opacity-50" />
          </label>
          <label class="flex items-center justify-between gap-2 text-xs font-medium text-slate-300" for="cad-via-annular-ring">
            <span>Annular ring width (mm)<HelpTag label="About annular ring width" tip="Copper width on one side of the hole. A 0.075 mm ring adds 0.15 mm to the via diameter, because it surrounds both sides." /></span>
            <input id="cad-via-annular-ring" aria-label="Annular ring width (mm)" type="text" inputmode="decimal" value={viaAnnularRingText} oninput={updateViaAnnularRing} disabled={busy} class="w-24 shrink-0 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 disabled:opacity-50" />
          </label>
        </ViaSizingGuide>
        </details>
        <label class="mt-3 flex items-center gap-2 text-xs text-slate-300">
          <input type="checkbox" aria-label="Simplify collinear lines on import" title="Merge touching straight lines in the same coil and layer. Gaps are kept." checked={simplifyLines} disabled={busy} onchange={(event) => { simplifyLines = event.currentTarget.checked; schedulePreviewRefresh(); }} />
          Simplify lines
        </label>
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
        <section class="border-t border-slate-700 pt-3" aria-label="Source layer coil assignments">
          <h3 class="text-xs font-medium text-slate-100" title="Source layers with the same coil name belong together. Copper layers come from Z heights.">Source coils</h3>
          <div class="mt-3 grid gap-2">
            {#each Object.entries(imported.geometry.source_layer_coils ?? {}) as [name, coil] (name)}
              <label class="flex items-center justify-between gap-3 text-xs text-slate-300">
                <span class="min-w-0 break-all font-mono">{name}</span>
                <input aria-label={`Coil for source layer ${name}`} value={Object.hasOwn(sourceLayerCoils, name) ? sourceLayerCoils[name] : coil} oninput={(event) => assignSourceLayer(name, event.currentTarget.value)} disabled={busy} class="w-28 shrink-0 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100" />
              </label>
            {/each}
          </div>
          {#if Object.values(sourceLayerCoils).some((coil) => !coil.trim())}
            <p role="alert" class="mt-2 text-xs text-rose-200">Enter a coil name for every source layer assignment.</p>
          {/if}
        </section>
      {/if}
      </aside>
      <main class="flex min-h-0 min-w-0 flex-col overflow-hidden p-3">
      {#if imported}
        <section class="flex min-h-0 flex-1 flex-col gap-3" aria-label="CAD import preview">
          <GeometryEditingToolbar label="CAD import tools" geometry={imported.geometry} {selection} {measure} {terminalTool}
            disabled={busy || !previewIsCurrent} onStartTerminals={startTerminals} onSimplify={simplifyTool.simplify}
            onUndoSimplify={simplifyTool.canUndo ? simplifyTool.undo : undefined} simplifyNotice={simplifyTool.notice} />
          {#if terminalTool.active}
            <CoilTerminalPanel tool={terminalTool} />
          {/if}
          <div class="relative flex min-h-0 flex-1 overflow-hidden rounded-md border border-slate-700 bg-slate-950 pr-11">
          <PreviewFrame bind:frame={previewFrameRef} bind:width={previewWidth} bind:height={previewHeight}
            {gestures} {measure} interactive={terminalTool.active} label="CAD import preview">
            <svg
              viewBox={`0 0 ${viewportWidth} ${viewportHeight}`}
              aria-hidden="true"
              preserveAspectRatio="xMidYMid meet"
              class="block h-full w-full"
            >
              <g transform={`matrix(${worldTransform.s} 0 0 ${-worldTransform.s} ${worldTransform.tx + gestures.panX} ${worldTransform.ty + gestures.panY})`}>
                {#each imported.geometry.layer_z_mm as _, layer (layer)}
                  {#if previewView.isLayerVisible(layer)}
                    <g fill="none" stroke-width={renderedStrokeWidth} stroke-linecap="round" stroke-linejoin="round">
                      {#each joinedPreview.segments.filter((segment) => segment.layer === layer && traceVisible(segment.net, layer)) as segment (segment)}
                        <path stroke={coilColor(segment.net)} d={`M ${segment.start.x} ${segment.start.y} L ${segment.end.x} ${segment.end.y}`} />
                      {/each}
                      {#each joinedPreview.curves.filter((curve) => curve.layer === layer && traceVisible(curve.net, layer)) as curve (curve)}
                        <path stroke={coilColor(curve.net)} d={arcSvgPath(curve)} />
                      {/each}
                      {#each (imported.geometry.routing.splines ?? []).filter((spline) => spline.layer === layer && traceVisible(spline.net, layer)) as spline (spline)}
                        <path stroke={coilColor(spline.net)} d={splineSvgPath(spline)} />
                      {/each}
                    </g>
                  {/if}
                {/each}
                {#if previewView.showVias}
                <g fill="#fbbf24" stroke="#0f172a" stroke-width={previewStrokeWidth * 0.25}>
                  {#each imported.geometry.routing.vias.filter((via) => traceVisible(via.net, via.from_layer) || traceVisible(via.net, via.to_layer)) as via (via)}
                    <circle fill={coilColor(via.net)} cx={via.position.x} cy={via.position.y} r={viaPadRadius} />
                  {/each}
                </g>
                <g fill="#020617" stroke="#0f172a" stroke-width={previewStrokeWidth * 0.2}>
                  {#each imported.geometry.routing.vias.filter((via) => traceVisible(via.net, via.from_layer) || traceVisible(via.net, via.to_layer)) as via (via)}
                    <circle cx={via.position.x} cy={via.position.y} r={viaDrillRadius} />
                  {/each}
                </g>
                {/if}
              </g>
            </svg>
            <GeometryEditingOverlay geometry={imported.geometry} {selection} {terminalTool} transform={worldTransform} panX={gestures.panX} panY={gestures.panY} width={viewportWidth} height={viewportHeight} isVisible={traceVisible} disabled={busy || !previewIsCurrent || measure.mode} />
            <PreviewMeasureOverlay {measure} transform={worldTransform} panX={gestures.panX} panY={gestures.panY} width={viewportWidth} height={viewportHeight} metresToWorld={1000} />
          </PreviewFrame>
            <PreviewLayersPopover
              label="CAD import layers"
              geometry={imported.geometry} {selection} assignmentDisabled={busy || !previewIsCurrent || measure.mode || terminalTool.active}
              view={previewView}
              layers={previewLayers}
              coils={previewCoils.map((name, colorIdx) => ({ name, colorIdx }))}
              isCoilVisible={(name) => !coilHidden(name)}
              onToggleCoil={(name) => { hiddenCoils = { ...hiddenCoils, [name]: !coilHidden(name) }; }}
            />
          </div>
          <div class="flex flex-wrap items-center justify-end gap-3">
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
          {#if Object.keys(imported.geometry.coil_terminals ?? {}).length}
            <div class="max-h-24 shrink-0 overflow-y-auto overscroll-contain">
              <CoilTerminalSummary geometry={imported.geometry} tool={terminalTool} onEdit={startTerminals} onGeometryChange={updateImportedGeometry} />
            </div>
          {/if}
          {#if !viaSizingValid}
            <p role="alert" class="text-xs text-rose-200">Via drill and annular ring must be positive values.</p>
          {/if}
          {#if !previewIsCurrent}
            <p role="status" class="text-xs text-amber-200">{edited ? "Settings changed. Reimport to replace your segment edits." : "Updating preview…"}</p>
          {/if}
          {#if imported.warnings.length > 0}
            <details class="max-h-24 shrink-0 overflow-y-auto rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
              <summary class="cursor-pointer">{imported.warnings.length} import warnings</summary>
              <ul class="mt-1 list-inside list-disc text-[11px] text-amber-200/80">
                {#each imported.warnings.slice(0, 3) as warning (warning)}<li>{warning}</li>{/each}
              </ul>
            </details>
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
      </main>
    </div>

    <div class="flex shrink-0 flex-wrap items-center gap-3 border-t border-slate-700 px-4 py-2 text-xs text-slate-400">
      <label class="flex items-center gap-2">DXF units
        <select id="cad-units" aria-label="DXF units" bind:value={unitsToMm} onchange={schedulePreviewRefresh} disabled={busy} title="Choose the units used in the source DXF. Imported geometry is stored in millimetres." class="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200">
          <option value="1">Millimetres</option><option value="25.4">Inches</option>
        </select>
      </label>
      {#if imported}<span>{imported.geometry.routing.segments.length} lines, {imported.geometry.routing.curves.length} arcs, {imported.geometry.routing.splines?.length ?? 0} splines, {imported.geometry.routing.vias.length} vias</span><span>{imported.geometry.layer_z_mm.length} copper layers</span>{/if}
    </div>
    <footer class="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-slate-800 px-5 py-3 md:px-7">
      <div class="flex flex-wrap gap-2">
        <button type="button" onclick={onClose} disabled={busy} class="rounded-md px-3 py-2 text-xs text-slate-400 hover:bg-slate-800 hover:text-slate-100 disabled:opacity-50">Cancel</button>
        {#if existingGeometry}
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
          {#if edited}<button type="button" onclick={refreshPreview} disabled={busy || !importSettingsValid} class="rounded-md border border-amber-500/40 px-3 py-2 text-xs text-amber-200">Reimport</button>{:else}<span role="status" class="px-3 py-2 text-xs text-slate-400">Updating preview…</span>{/if}
        {:else}
          <button type="button" onclick={chooseCadFile} disabled={busy || !importSettingsValid} class="rounded-md border border-sky-500/50 bg-sky-600/30 px-4 py-2 text-xs font-medium text-sky-100 hover:bg-sky-500/40 disabled:opacity-50">{busy ? "Preparing preview…" : "Choose DXF…"}</button>
        {/if}
      </div>
    </footer>
  </div>
</div>

<style>
  .import-layout { display: grid; grid-template-columns: 17rem minmax(0, 1fr); grid-template-rows: minmax(0, 1fr); }
  .import-settings :global(.via-guide) { grid-template-columns: minmax(0, 1fr) 5rem; gap: .5rem; }
  .import-settings :global(.via-inputs label) { flex-direction: column; align-items: flex-start; }
  .import-settings :global(.via-inputs input) { width: 100%; }
  @media (max-width: 640px) {
    .import-layout { grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(0, 8rem) minmax(0, 1fr); }
    .import-settings { border-right: 0; border-bottom: 1px solid rgb(var(--slate-700)); }
  }
</style>
