<!--
  ═══════════════════════════════════════════════════════════════════════
  Canvas coil viewer (inline card + lightbox host).

  Layers are drawn OVERLAID at their TRUE coordinates (a top-down view
  matching the DXF export). Per-layer show/hide toggles let you inspect
  each copper layer alone.

  This file is the composition root: it owns the geometry derivation, the
  frame/canvas refs, ResizeObserver sizing and the draw effect for the
  dual-instance inline/modal draw pattern, and it instantiates the shared
  helpers both views read:
    - lib/previewGeometry.ts            — pure, tested geometry derivation
    - ./coilPreviewCanvas.ts            — the canvas paint routines
                                          (CoilPreviewRenderer, extracted
                                          from this file's former ~400-line
                                          `drawInto`)
    - lib/utils/coilPreviewGestures     — pan/pinch/scroll-zoom state machine
    - lib/utils/coilPreviewMeasure      — lightbox two-click measure ruler
    - ./coilPreviewViewState.svelte.ts  — presentation toggles shared by the
                                          inline card and the lightbox
    - ./CoilPreviewLightbox.svelte      — the Bits UI Dialog lightbox (the
                                          expanded view hosts ALL interactive
                                          presentation toggles there)

  Interaction: one pointer (mouse / pen / lone touch) drags to pan; a
  two-finger pinch or a ctrl+wheel trackpad pinch zooms CONTINUOUSLY
  (clamped 0.5×…10×) with focal-point anchoring. All gesture behavior —
  touch/pointer ownership, pointer-capture cleanup, pan/pinch/focal math —
  lives in lib/utils/coilPreviewGestures.svelte; this file only binds the
  gesture handlers and renders the reactive view state.
  ═══════════════════════════════════════════════════════════════════════
-->
<script lang="ts">
  import { confirm } from "@tauri-apps/plugin-dialog";
  import { untrack } from "svelte";
  import type { Snippet } from "svelte";
  import { isDesignPanel, isLeftPanel, type DesignPanelId, type PreviewPanelId } from "./previewPanels";
  import type { PreviewCamera } from "../../utils/coilPreviewGestures.svelte";
  import { editableCoilGeometry } from "../../ipc/dxf";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { MotionStore } from "../../stores/motion.svelte";
  import type { CadGeometry, CoilPathDto, DriveAnalysis } from "../../types";
  import { CadSimplifyTool } from "../../utils/cadSimplifyTool.svelte";
  import { CoilTerminalTool } from "../../utils/coilTerminalTool.svelte";
  import { withAutomaticCadTerminals } from "../../cadTerminals";
  import { generatedTerminalGeometry } from "../../generatedTerminalGeometry";
  import {
    clientToVirtual,
    computePreviewGeometry,
    computeMagnets,
    computeUniqueLayers,
    computeUniquePhases,
    computeVisibleSegments,
    computeVisibleArcs,
    computePolePitchRuler,
    computeBandWidthRows,
    computeOverlayFitBounds,
    computeMoverStripBounds,
    computePoleRegionZones,
    computePoleRegionPhases,
    filterPoleRegionsByPhase,
    resolvePoleRegionPhaseSelection,
    virtualToWorld,
    firstMagnetCenterX as magnetCenterX,
    type PreviewConfigLike,
  } from "../../previewGeometry";
  import type { WorldTransform } from "../../chart";
  import { fitWorldToView, unionBounds } from "../../chart";
  import { CoilPreviewGestures } from "../../utils/coilPreviewGestures.svelte";
  import { CoilPreviewMeasure } from "../../utils/coilPreviewMeasure.svelte";
  import CoilPreviewLightbox from "./CoilPreviewLightbox.svelte";
  import CoilPreviewIsoView from "./CoilPreviewIsoView.svelte";
  import PreviewFrame from "./PreviewFrame.svelte";
  import {
    PREVIEW_H,
    PREVIEW_W,
    CoilPreviewRenderer,
    bandRowInOnePeriod,
  } from "./coilPreviewCanvas";
  import { CoilPreviewViewState } from "./coilPreviewViewState.svelte";

  let {
    config,
    coils,
    motion,
    expanded = $bindable(false),
    workspace = false,
    active = true,
    designSettings,
    sidePanel = $bindable<PreviewPanelId | null>(null),
    drive = null,
    driveError = null,
    drivePending = false,
    importedGeometry = null,
    onGeometryChange,
    camera,
    view = new CoilPreviewViewState(),
  }: { config: ConfigStore; coils: CoilPathDto | null; motion: MotionStore; expanded?: boolean; workspace?: boolean; active?: boolean; designSettings?: Snippet<[DesignPanelId]>; sidePanel?: PreviewPanelId | null; drive?: DriveAnalysis | null; driveError?: string | null; drivePending?: boolean; importedGeometry?: CadGeometry | null; onGeometryChange?: (geometry: CadGeometry) => void; camera?: PreviewCamera; view?: CoilPreviewViewState } =
    $props();

  export function showDesignSettings(section: DesignPanelId = "constraints"): void { sidePanel = section; }

  const simplifyTool = new CadSimplifyTool({ getGeometry: () => importedGeometry, onChange: (geometry) => onGeometryChange?.(geometry) });
  let canUndoSimplify = $derived(simplifyTool.canUndo);
  let simplifyNotice = $derived(simplifyTool.notice);
  async function startSegmentEditing(): Promise<boolean> {
    if (!onGeometryChange) return false;
    const accepted = await confirm("Create editable geometry? Segment edits will stop following routing settings. Choose a generator in Design settings to return to generated geometry.", { title: "Edit generated segments", kind: "warning", okLabel: "Create editable geometry", cancelLabel: "Keep generated" });
    if (!accepted) return false;
    const requested = config.toIpc();
    const requestedKey = JSON.stringify(requested);
    const geometry = await editableCoilGeometry(requested);
    if (requestedKey !== JSON.stringify(config.toIpc()) || importedGeometry) throw new Error("The design changed. Try editing segments again.");
    onGeometryChange(geometry);
    return true;
  }
  function simplifyImportedLines(): void {
    if (onGeometryChange) simplifyTool.simplify();
  }
  function undoSimplify(): void {
    if (onGeometryChange) simplifyTool.undo();
  }

  // Virtual drawing space. The CSS box keeps the same 760:260 aspect ratio as
  // the old SVG viewBox; every overlay (legend, disclaimer) is laid out in
  // these virtual px so it matches the SVG markup exactly. The paint routines
  // live in ./coilPreviewCanvas.ts, which shares these constants.
  const W = PREVIEW_W;
  let viewportWidth = $state(PREVIEW_W);
  let viewportHeight = $state(PREVIEW_H);
  const interactive = $derived(workspace || expanded);
  const H = $derived(interactive && viewportWidth > 0 ? W * viewportHeight / viewportWidth : PREVIEW_H);
  const PAD = 30;

  // -------------------------------------------------------------------
  // Shared presentation state (CoilPreviewViewState instance): the
  // schematic toggles + per-phase/per-layer trace visibility for BOTH
  // views. The toggles live in the lightbox UI; the draw effect below
  // reads the same instance, so a flip there repaints the schematic.
  // -------------------------------------------------------------------
  let terminalGeometry = $derived(importedGeometry ? withAutomaticCadTerminals(importedGeometry) : coils ? generatedTerminalGeometry(coils, config.num_layers, config.pcb_thickness_mm, config.trace_width_mm, config.routing_pattern === "infinity-braid" ? config.routing_params.connection : undefined) : null);
  const terminalTool = new CoilTerminalTool({
    getGeometry: () => terminalGeometry,
    onChange: (geometry) => onGeometryChange?.(geometry),
    onReveal: (coil, layer) => {
      const phase = coils?.phases.find((p) => p.phase_name === coil);
      if (phase) view.phaseVisibility[phase.phase_idx] = true;
      view.layerVisibility = { ...view.layerVisibility, [layer]: true };
      view.showCoilLayer(coil, layer);
    },
    onFit: () => gestures.resetView(),
  });
  function startTerminalTool(coil?: string): void {
    if (!terminalGeometry || !onGeometryChange) return;
    view.viewMode = "top";
    measure.mode = false;
    measure.clear();
    view.oneSection = false;
    if (!workspace) expanded = true;
    terminalTool.begin(coil);
  }
  // An ends request from elsewhere (the Simulation tab's alert) opens the
  // expanded viewer with the coil-ends panel ready.
  $effect(() => {
    const request = view.terminalRequest;
    if (!request) return;
    untrack(() => startTerminalTool(view.requestedTerminalCoil));
  });
  // A generated pattern is re-derived on every parameter edit. Re-anchor the
  // open terminal tool so its automatic ends reselect instead of going stale.
  $effect(() => {
    const geometry = terminalGeometry;
    untrack(() => terminalTool.rebind(geometry));
  });
  function isTerminalVisible(coil: string, layer: number): boolean {
    const phase = coils?.phases.find((p) => p.phase_name === coil);
    return Boolean(phase && view.isPhaseVisible(phase.phase_idx) && view.isLayerVisible(layer) && view.isCoilLayerVisible(coil, layer));
  }

  // -------------------------------------------------------------------
  // Zoom bounds + button steps. The actual zoom state, pan, pinch and
  // scroll-zoom logic live in lib/utils/coilPreviewGestures.svelte — this
  // component only supplies the geometry transform + constants and forwards
  // DOM events to the gesture class. `zoom` is CONTINUOUS (0.5…10): the
  // buttons step through ZOOM_STEPS, while pinches are continuous.
  const MIN_ZOOM = 0.5;
  const MAX_ZOOM = Infinity;
  const ZOOM_STEPS = [0.5, 1, 1.5, 2, 3, 4, 6, 8, 10] as const;

  /** One repeating unit of the winding = max(6, 2 × phases) conductors. */
  let oneSectionConductorCount = $derived(Math.max(6, 2 * config.phases));

  // -------------------------------------------------------------------
  // Geometry + view — ALL math comes from lib/previewGeometry + lib/chart.
  // `config` (ConfigStore) satisfies PreviewConfigLike structurally (it has
  // magnet_count / magnet_width_mm / magnet_gap_mm plus extras, which is
  // fine for structural typing). Magnet placement also consumes the generated
  // routing_dimensions sidecar when available: each pitch cell's right edge
  // (solid bar + trailing gap) is anchored to the pattern's B-phase leg
  // centres so the poles stay locked to the leg zones. Legacy or missing
  // sidecars use computeMagnets' centered pitch-cell fallback.
  // -------------------------------------------------------------------
  let g = $derived(computePreviewGeometry(coils, config as PreviewConfigLike));

  /** World→virtual transform for a zoom level, using the CURRENT geometry
   *  (backed by lib/chart fitWorldToView; injected into the gesture class).
   *  `overlayFitBounds` unions the schematic fit box with any
   *  `routing_dimensions` overlay geometry (pole-pitch ruler, band-width
   *  rows, pole regions) so the camera never clips an annotation. */
  function worldTransformFor(zoom: number): WorldTransform {
    const drawerWidth = isDesignPanel(sidePanel) ? 400 : sidePanel ? 240 : 0;
    const leftInset = interactive && designSettings ? 44 + (isLeftPanel(sidePanel) ? Math.min(drawerWidth, Math.max(0, viewportWidth - 132)) : 0) : 0;
    const inset = interactive ? leftInset + 44 + (sidePanel && !isLeftPanel(sidePanel) ? Math.min(drawerWidth, Math.max(0, viewportWidth - 132)) : 0) : 0;
    const fitWidth = W * Math.max(0.15, 1 - inset / Math.max(viewportWidth, 1));
    const fit = (bounds: typeof overlayFitBounds) => {
      const transform = fitWorldToView(bounds, fitWidth, H, PAD, zoom);
      return { ...transform, tx: transform.tx + W * leftInset / Math.max(viewportWidth, 1) };
    };
    // A command focuses the selected coil, not the unrelated magnet array.
    if (terminalTool.active && terminalTool.coil) {
      const points = terminalTool.candidates.map((p) => p.position);
      if (points.length) {
        const xs = points.map((p) => p.x * 1e-3);
        const ys = points.map((p) => p.y * 1e-3);
        const minX = Math.min(...xs), maxX = Math.max(...xs);
        const minY = Math.min(...ys), maxY = Math.max(...ys);
        const pad = Math.max(maxX - minX, maxY - minY, 0.001) * 0.08;
        return fit({ minX: minX - pad, minY: minY - pad, maxX: maxX + pad, maxY: maxY + pad });
      }
    }
    return fit(overlayFitBounds);
  }

  // All pan/pinch/zoom state, cursor maths, touch/pointer coordination and
  // pointer-capture cleanup live in the gesture utility; this component only
  // reads its reactive view state and binds its handlers.
  const gestures = new CoilPreviewGestures({
    camera: untrack(() => camera),
    get interactionMode() { return interactive ? "cad" : "navigation"; },
    virtualW: W,
    get virtualH() { return H; },
    minZoom: MIN_ZOOM,
    maxZoom: MAX_ZOOM,
    zoomSteps: ZOOM_STEPS,
    getWorldTransform: worldTransformFor,
  });

  let worldTransform = $derived(worldTransformFor(gestures.zoom));
  let magnets = $derived(computeMagnets(config, coils?.routing_dimensions));
  // The mover position from the shared MotionStore places the whole strip in
  // ABSOLUTE track coordinates: bar 0's left edge lands exactly at
  // `motion.stripStartMm` (= position − mover_span/2), matching the design
  // reflection's iso view and readouts. Polarity order and pitch come from
  // the pattern-anchored `computeMagnets` layout.
  let visibleMagnets = $derived.by(() => {
    if (magnets.length === 0) return magnets;
    const restStartM = Math.min(...magnets.map((m) => m.x));
    const targetStartM = motion.stripStartMm / 1000;
    return magnets.map((m) => ({ ...m, x: m.x + targetStartM - restStartM }));
  });
  // Camera-fit extreme: the largest leading-edge shift of either travel end
  // relative to the pattern-anchored rest layout, so reset-view never clips
  // the moved magnets.
  let maxMoverOffsetM = $derived.by(() => {
    const halfSpanM = config.mover_span_mm / 2000;
    const restStartM =
      magnets.length > 0 ? Math.min(...magnets.map((m) => m.x)) : 0;
    const leadAtMin = motion.moverMinMm / 1000 - halfSpanM - restStartM;
    const leadAtMax = motion.moverMaxMm / 1000 - halfSpanM - restStartM;
    return Math.max(0, leadAtMin, leadAtMax);
  });
  let uniquePhases = $derived(computeUniquePhases(coils));
  let uniqueLayers = $derived(computeUniqueLayers(coils));

  // Header stat line, shared verbatim by the inline card and the lightbox.
  let stats = $derived(
    coils
      ? `${uniquePhases.length} phase${uniquePhases.length === 1 ? "" : "s"} · ${g.renderedLayerCount} layer${g.renderedLayerCount === 1 ? "" : "s"} · ${coils.phases.length} coil group${coils.phases.length === 1 ? "" : "s"}`
      : "no coils yet",
  );

  let visibleSegments = $derived(
    computeVisibleSegments(coils, view.oneSection, oneSectionConductorCount),
  );
  let visibleArcs = $derived(
    computeVisibleArcs(coils, view.oneSection, oneSectionConductorCount),
  );

  // -------------------------------------------------------------------
  // routing_dimensions sidecar overlays: pole-pitch ruler, band-width rows,
  // and pattern-owned pole-region zones.
  // Pure world-space geometry from lib/previewGeometry; resistant to an
  // absent/legacy sidecar (null sidecars → no ruler, no rows). The camera
  // fit always includes them so reset-view never clips an annotation.
  // -------------------------------------------------------------------
  let firstMagnetCentreX = $derived(magnetCenterX(visibleMagnets));
  let poleRuler = $derived(
    computePolePitchRuler(
      coils?.routing_dimensions,
      firstMagnetCentreX,
      g.fitBounds.maxY + 0.0008, // just above the magnet strip
    ),
  );
  let bandRows = $derived(
    computeBandWidthRows(coils, coils?.routing_dimensions),
  );

  // Pole-region zones (pattern-owned phase/pole boundaries from the routing
  // sidecar). `view.poleRegionPhase` is the phase-picker selection; "" =
  // "All phases". Draws only the selected phase's zones. Independent of the
  // per-phase trace visibility toggles.
  let poleRegionZones = $derived(
    computePoleRegionZones(coils?.routing_dimensions),
  );
  let hasPoleRegionData = $derived(poleRegionZones.length > 0);
  let poleRegionPhases = $derived(computePoleRegionPhases(poleRegionZones));
  let visiblePoleRegionZones = $derived(
    filterPoleRegionsByPhase(poleRegionZones, view.poleRegionPhase),
  );

  /** Guarded sync so the picker stays valid when a regenerated payload ships
   *  different phase labels: if the selected label is gone, collapse back to
   *  "All phases". Reads + writes `view.poleRegionPhase`; the write only
   *  happens on the invalid branch so the effect terminates (no update
   *  cycle). */
  $effect(() => {
    const resolved = resolvePoleRegionPhaseSelection(
      view.poleRegionPhase,
      poleRegionPhases,
    );
    if (resolved !== view.poleRegionPhase) view.poleRegionPhase = resolved;
  });

  let overlayFitBounds = $derived.by(() => {
    const base = computeOverlayFitBounds(
      computeMoverStripBounds(
        g.fitBounds,
        magnets,
        maxMoverOffsetM,
        g.magnetTop,
        0.003,
      ),
      // Fit diagnostics only in the expanded viewer; the small preview is geometry-only.
      interactive ? poleRuler : null,
      interactive ? bandRows : [],
      interactive ? poleRegionZones : [],
      g.boardRect.y,
      g.boardRect.y + g.boardRect.h,
    );
    return lockedMeasureBounds ? unionBounds(base, lockedMeasureBounds) : base;
  });
  let hasPolePitchData = $derived(poleRuler !== null);
  let hasBandWidthData = $derived(bandRows.length > 0);

  // Band rows the renderer paints: phase/layer visibility + the one-section
  // window filter (pure helper lives in ./coilPreviewCanvas.ts).
  let visibleBandRows = $derived(
    view.showBandWidths
      ? bandRows.filter(
          (row) =>
            view.isPhaseVisible(row.phaseIdx) &&
            view.isLayerVisible(row.layer) &&
            view.isCoilLayerVisible(coils?.phases.find((ph) => ph.phase_idx === row.phaseIdx)?.phase_name ?? "", row.layer) &&
            bandRowInOnePeriod(row, view.oneSection, visibleSegments),
        )
      : [],
  );

  // -------------------------------------------------------------------
  // Workspace measure ruler. Two-click dimension tool: click 1 sets the
  // start point, click 2 locks the dimension, click 3 clears it. The
  // reset button (visible while measure mode is on) clears without a
  // click. Taps are distinguished from pan-drags by a movement threshold,
  // so pan/pinch/zoom keep working while measuring. Shared by the full-tab
  // workspace and expanded viewer.
  //
  // ALL measure state + tap bookkeeping (mode, points, live cursor,
  // pointer/touch maps, tap threshold) lives in the utility class
  // lib/utils/coilPreviewMeasure.svelte — extracted the same way as the
  // gesture utility. This component only injects the client→world mapping
  // through the CURRENT camera (pure previewGeometry math); the lightbox
  // forwards the modal frame's pointer/touch events to it.
  // -------------------------------------------------------------------
  const measure = new CoilPreviewMeasure({
    screenToWorld: (clientX, clientY) => {
      const frame = activeFrame;
      if (!frame) return null;
      const rect = frame.getBoundingClientRect();
      const v = clientToVirtual(clientX, clientY, rect, W, H);
      return virtualToWorld(
        v.x,
        v.y,
        worldTransform,
        gestures.panX,
        gestures.panY,
      );
    },
  });

  /** Locked-dimension fit bounds (camera-fit input, lightbox only). */
  let lockedMeasureBounds = $derived(
    interactive && measure.mode && measure.lockedBounds
      ? measure.lockedBounds
      : null,
  );

  // -------------------------------------------------------------------
  // Frame + backing-store sizing. A ResizeObserver keeps the canvas backing
  // store in lockstep with the rendered CSS box (dpr-capped at 2×); writing
  // `frameRevision` re-triggers the draw effect below.
  //
  // One ResizeObserver follows the active frame, either the embedded
  // workspace or expanded viewer. Sizing writes happen in its callback;
  // switching views disconnects the old observer before observing the new frame.
  // -------------------------------------------------------------------
  let frameRef: HTMLDivElement | undefined = $state();
  let canvasRef: HTMLCanvasElement | undefined = $state();
  let modalFrameRef: HTMLDivElement | undefined = $state();
  let modalCanvasRef: HTMLCanvasElement | undefined = $state();
  let frameRevision = $state(0);

  // The pair that is currently visible: the inline canvas while collapsed,
  // the modal canvas while expanded. The draw effect paints only this pair.
  let activeFrame = $derived(expanded ? modalFrameRef : frameRef);
  let activeCanvas = $derived(expanded ? modalCanvasRef : canvasRef);

  $effect(() => {
    const frame = activeFrame;
    const canvas = activeCanvas;
    if (!frame) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    // All sizing happens inside the RO callbacks only (no state writes in the
    // effect body). observe() guarantees an initial delivery before paint, so
    // the backing store + `frameRevision` (which re-triggers the draw effect) are
    // always set before the first render is presented.
    const observer = new ResizeObserver(() => {
      if (frame.clientWidth <= 0 || frame.clientHeight <= 0) return;
      if (canvas) {
        canvas.width = Math.round(frame.clientWidth * dpr);
        canvas.height = Math.round(frame.clientHeight * dpr);
      }
      frameRevision += 1;
      viewportWidth = frame.clientWidth;
      viewportHeight = frame.clientHeight;
    });
    observer.observe(frame);
    return () => observer.disconnect();
  });

  // -------------------------------------------------------------------
  // Canvas rendering — the paint routines live in ./coilPreviewCanvas.ts
  // (`CoilPreviewRenderer`, extracted verbatim from the former `drawInto`).
  // This component owns the dual-instance inline/modal draw pattern: the
  // frame/canvas refs, the ResizeObserver sizing above, and the draw effect
  // below, which builds the per-tick `CoilPreviewDrawInput` snapshot and
  // paints the ACTIVE pair only. One renderer instance per component: its
  // revision counter is shared across the inline and modal canvases.
  // -------------------------------------------------------------------
  const renderer = new CoilPreviewRenderer();

  // Redraw whenever any input to the schematic changes. Draws the ACTIVE
  // canvas only — the inline pair while collapsed, the modal pair while
  // expanded. All reads below happen synchronously so Svelte auto-tracks
  // them (including the ones the renderer consumes through the visibility
  // callbacks). Runs even without coils so the "Awaiting coil generation…"
  // placeholder paints on the empty active canvas.
  $effect(() => {
    const frame = activeFrame;
    const canvas = activeCanvas;
    // Keep resize tracking even while hidden. Otherwise the zero-width guard
    // drops this dependency and a same-size return leaves a cleared canvas.
    void frameRevision;
    if (!active) return;
    if (!frame || !canvas) return;
    if (frame.clientWidth <= 0) return;
    void worldTransform;
    void gestures.panX;
    void gestures.panY;
    void view.oneSection;
    void view.phaseVisibility;
    void view.layerVisibility;
    void view.showVias;
    void view.showPolePitch;
    void view.showBandWidths;
    void view.showPoleRegions;
    void view.poleRegionPhase;
    void visiblePoleRegionZones;
    void visibleSegments;
    void visibleArcs;
    void visibleMagnets;
    void poleRuler;
    void bandRows;
    void overlayFitBounds;
    void g;
    void expanded;
    renderer.draw(frame, canvas, {
      coils,
      activeAreaLengthMm: config.active_area_length_mm,
      geometry: g,
      worldTransform,
      panX: gestures.panX,
      panY: gestures.panY,
      visibleMagnets,
      visibleSegments,
      visibleArcs,
      isPhaseVisible: (phaseIdx) => view.isPhaseVisible(phaseIdx),
      isLayerVisible: (layerIdx) => view.isLayerVisible(layerIdx),
      isCoilLayerVisible: (coil, layer) => view.isCoilLayerVisible(coil, layer),
      showVias: view.showVias,
      traceMode: view.traceMode,
      traceWidthMm: config.trace_width_mm,
      viaDrillMm: config.min_via_drill_mm,
      viaAnnularRingMm: config.min_via_annular_ring_mm,
      poleRuler,
      showPolePitch: interactive && view.showPolePitch,
      bandRows: interactive ? visibleBandRows : [],
      poleRegions: interactive && view.showPoleRegions ? visiblePoleRegionZones : [],
      measure: null,
    });
  });

  // -------------------------------------------------------------------
  // Interaction — ALL pan/pinch/scroll-zoom logic, touch↔pointer
  // coordination, pointer-capture cleanup and cursor math lives in
  // lib/utils/coilPreviewGestures.svelte. The component merely forwards the
  // DOM events below and reads the gesture instance's reactive state
  // (gestures.zoom / gestures.panX / gestures.panY / gestures.isPanning).
  // -------------------------------------------------------------------

  /** Double-clicking the inline preview opens the expanded lightbox. */
  function onInlineDoubleClick() {
    expanded = true;
  }

</script>

{#if workspace}
  <div class="h-full min-h-0">{#if !expanded}{@render viewer(true)}{/if}</div>
{:else}
<div class="rounded-lg bg-slate-800/40 border border-slate-700 p-4">
  <!-- The inline preview is read-only. Tools live in the expanded viewer. -->
  <div class="flex items-center justify-between mb-2 flex-wrap gap-2">
    <h3 class="text-sm font-semibold text-slate-200">Coil Preview</h3>
    <div class="flex items-center gap-2">
      <span class="text-xs text-slate-400">
        {stats}
      </span>
      <button
        type="button"
        class="px-2 py-0.5 text-xs rounded bg-slate-800 border border-slate-700 text-slate-300 hover:text-emerald-300 hover:border-emerald-600 transition-colors"
        aria-label="Expand coil preview"
        aria-expanded={expanded}
        onclick={() => (expanded = true)}>⤢</button
      >
    </div>
  </div>

  <!-- Frame div owns the ARIA label (the canvas is the paint surface; data-*
       attributes on the canvas carry the introspection counters). All pan/
       pinch/scroll-zoom handling is delegated to the gesture utility. -->
  <PreviewFrame bind:frame={frameRef} {gestures} navigationEnabled={view.viewMode === "top"} label="Coil preview" aspectRatio={W / PREVIEW_H} ondblclick={onInlineDoubleClick}>
    <!-- data-segments / data-vias / data-pole-pitch / data-band-widths /
         data-pole-regions / data-revision are written imperatively by the
         renderer (canvas.dataset in coilPreviewCanvas.ts), NOT bound
         reactively — see the counter comment there. -->
    {#if view.viewMode === "iso"}
      <CoilPreviewIsoView geometry={terminalGeometry} {view} isVisible={isTerminalVisible} showTerminals={false} />
    {:else}
      <canvas bind:this={canvasRef} class="block h-full w-full"></canvas>
    {/if}
  </PreviewFrame>

  {#if coils && coils.phases.length > 0}
    <p class="mt-2 text-xs text-slate-500">
      <span class="text-slate-600"
        >{view.viewMode === "iso" ? "Drag to orbit · Scroll or pinch to zoom · Switch to Top-down to edit" : "Drag to pan · Pinch or Ctrl-scroll to zoom · Expand to edit"}</span
      >
    </p>
  {/if}

</div>
{/if}

{#if expanded}{@render viewer(false)}{/if}

{#snippet viewer(inline: boolean)}
    <CoilPreviewLightbox
      embedded={inline}
      {active}
      {designSettings}
      bind:sidePanel
      bind:expanded
      height={H}
      {config}
      {drive}
      {driveError}
      {drivePending}
      {motion}
      {view}
      {gestures}
      {measure}
      onSimplify={importedGeometry && onGeometryChange ? simplifyImportedLines : undefined}
      onUndoSimplify={canUndoSimplify ? undoSimplify : undefined}
      {simplifyNotice}
      terminalTool={terminalGeometry && onGeometryChange ? terminalTool : undefined}
      {terminalGeometry}
      onStartTerminals={startTerminalTool}
      {importedGeometry}
      {onGeometryChange}
      onStartSegmentEditing={onGeometryChange ? startSegmentEditing : undefined}
      {worldTransform}
      isTerminalVisible={isTerminalVisible}
      {stats}
      {uniquePhases}
      {uniqueLayers}
      {hasPolePitchData}
      {hasBandWidthData}
      {hasPoleRegionData}
      {poleRegionPhases}
      bind:modalFrameRef={() => inline ? frameRef : modalFrameRef, (ref) => { if (inline) frameRef = ref; else modalFrameRef = ref; }}
      bind:modalCanvasRef={() => inline ? canvasRef : modalCanvasRef, (ref) => { if (inline) canvasRef = ref; else modalCanvasRef = ref; }}
    />
{/snippet}
