<!--
  ═══════════════════════════════════════════════════════════════════════
  CoilPreviewLightbox — the expanded coil preview modal.

  Hosts the Bits UI Dialog (Dialog.Root/Portal/Overlay/Content) with the
  expanded frame + canvas pair, ALL interactive presentation toggles —
  per-phase, per-layer, via, pole-pitch, band-width and pole-region
   visibility, the pole-region phase picker, and the one-section toggle — and
  the measure-ruler toolbar. Those two UI clusters are components of their
  own (extracted in kata 426r — each renders exactly once, here):
     - ./CoilPreviewVisibilityPanel.svelte — the right-hand Layers panel controls,
      bound to the shared CoilPreviewViewState instance
    - ./CoilPreviewMeasureToolbar.svelte — the measure-ruler toolbar,
      bound to the shared CoilPreviewMeasure instance
  Zoom/reset controls live BELOW the canvas (identical to the inline
  card), and the mover slider joins the strip it moves via the shared
  MotionStore.

  The schematic state itself is shared: `view` (CoilPreviewViewState),
  `gestures` (CoilPreviewGestures) and `measure` (CoilPreviewMeasure) are
  instances owned by CoilPreview and passed down, so both view instances
  (inline frame + canvas and modal frame + canvas) always show the same
  live schematic. Only ONE pair is drawn per render tick — the `expanded`
  rune in the parent picks the active pair. The modal frame + canvas refs
  bind back up (`bind:modalFrameRef`/`bind:modalCanvasRef`) because the
  parent's ResizeObserver sizing + draw effect and the gesture wheel
  listener drive both pairs.

  Dismissal: a backdrop click, Escape, and the × close button all dismiss
  it through Bits' dismissible/escape layers — no custom keydown/
  pointerdown handlers live here. While expanded, the page behind the
  lightbox is scroll-locked by the custom refcounted helper (document
  overflow lock + backdrop wheel/touchmove guard), which stays the source
  of truth — Bits' built-in scroll lock is therefore disabled
  (`preventScroll={false}`).
  Assessed in kata 1jfa — Bits' lock is not a replacement: it only writes
  overflow/padding/pointer-events on <body> (never inline on <html>) and
  has no wheel/touchmove preventDefault, so the e2e contract's pinned
  invariants (inline root+body overflow lock, backdrop wheel
  defaultPrevented) fail without this helper (4/6 spec runs red under
  pure-Bits). It must not run alongside either: Bits' delayed body-style
  reset re-applies a stale snapshot and leaves the page scroll-locked
  after close.
  ═══════════════════════════════════════════════════════════════════════
-->
<script lang="ts">
  import { GitMerge, Undo2, Plug, X } from "@lucide/svelte";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { MotionStore } from "../../stores/motion.svelte";
  import { Dialog } from "bits-ui";
  import { onDestroy } from "svelte";
  import type { CadGeometry } from "../../types";
  import type { WorldTransform } from "../../chart";
  import type { CoilTerminalTool } from "../../utils/coilTerminalTool.svelte";
  import CoilTerminalPanel from "./CoilTerminalPanel.svelte";
  import CoilTerminalOverlay from "./CoilTerminalOverlay.svelte";
  import { assignCadTerminals, terminalDescription } from "../../cadTerminals";
  import type { CoilPreviewGestures } from "../../utils/coilPreviewGestures.svelte";
  import type { CoilPreviewMeasure } from "../../utils/coilPreviewMeasure.svelte";
  import {
    attachBackdropScrollGuard,
    lockPageScroll,
  } from "../../utils/pageScrollLock";
  import CoilPreviewControls from "./CoilPreviewControls.svelte";
  import CoilPreviewMeasureToolbar from "./CoilPreviewMeasureToolbar.svelte";
  import CoilPreviewVisibilityPanel from "./CoilPreviewVisibilityPanel.svelte";
  import MoverPositionControls from "./MoverPositionControls.svelte";
  import { PREVIEW_H, PREVIEW_W } from "./coilPreviewCanvas";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";
  import CadSelectionToolbar from "./CadSelectionToolbar.svelte";
  import CadSelectionOverlay from "./CadSelectionOverlay.svelte";

  let {
    expanded = $bindable(false),
    config,
    motion,
    view,
    gestures,
    measure,
    onSimplify,
    onUndoSimplify,
    simplifyNotice = "",
    terminalTool,
    onStartTerminals,
    importedGeometry = null,
    onGeometryChange,
    onStartSegmentEditing,
    worldTransform,
    isTerminalVisible,
    stats,
    uniquePhases,
    uniqueLayers,
    hasPolePitchData,
    hasBandWidthData,
    hasPoleRegionData,
    poleRegionPhases,
    modalFrameRef = $bindable(),
    modalCanvasRef = $bindable(),
  }: {
    /** Dialog open state, bound to the parent's `expanded` rune. */
    expanded?: boolean;
    config: ConfigStore;
    motion: MotionStore;
    view: CoilPreviewViewState;
    gestures: CoilPreviewGestures;
    measure: CoilPreviewMeasure;
    onSimplify?: () => void;
    onUndoSimplify?: () => void;
    simplifyNotice?: string;
    terminalTool?: CoilTerminalTool;
    onStartTerminals?: (coil?: string) => void;
    importedGeometry?: CadGeometry | null;
    onGeometryChange?: (geometry: CadGeometry) => void;
    onStartSegmentEditing?: () => Promise<boolean>;
    worldTransform: WorldTransform;
    isTerminalVisible: (coil: string, layer: number) => boolean;
    /** Header stat line ("N phases · N layers · N coil groups"), precomputed. */
    stats: string;
    uniquePhases: { idx: number; name: string; colorIdx: number }[];
    uniqueLayers: { idx: number }[];
    hasPolePitchData: boolean;
    hasBandWidthData: boolean;
    hasPoleRegionData: boolean;
    poleRegionPhases: string[];
    /** Expanded frame + canvas pair, driven by the parent's draw machinery. */
    modalFrameRef?: HTMLDivElement;
    modalCanvasRef?: HTMLCanvasElement;
  } = $props();

  // Virtual drawing space — same constants as the inline card (the CSS box
  // keeps the same 760:260 aspect ratio as the old SVG viewBox).
  const W = PREVIEW_W;
  const H = PREVIEW_H;
  const selection = new CadSelectionTool({ getGeometry: () => importedGeometry, onChange: (geometry) => onGeometryChange?.(geometry) });
  function activateSelection() { terminalTool?.cancel(); measure.mode = false; view.oneSection = false; }
  let preparingSegments = $state(false);
  let selectionError = $state("");
  async function prepareSegments() {
    preparingSegments = true;
    selectionError = "";
    try { if (await onStartSegmentEditing?.()) { activateSelection(); selection.setMode("select"); } }
    catch (e) { selectionError = e instanceof Error ? e.message : String(e); }
    finally { preparingSegments = false; }
  }
  onDestroy(() => terminalTool?.cancel());

  let backdropRef: HTMLDivElement | null = $state(null);
  let modalPanelRef: HTMLDivElement | null = $state(null);

  // Modal pointer/touch handlers compose the measure tool with the gesture
  // utility (order preserved from the pre-extraction implementation: taps
  // bookkeep before/after the gesture pass exactly as it did inline).
  function onModalPointerDown(e: PointerEvent) {
    measure.handlePointerDown(e);
    gestures.handlePointerDown(e);
  }

  function onModalPointerMove(e: PointerEvent) {
    measure.handlePointerMove(e);
    gestures.handlePointerMove(e);
  }

  function onModalPointerUp(e: PointerEvent) {
    gestures.handlePointerEnd(e);
    measure.handlePointerUp(e);
  }

  function onModalPointerCancel(e: PointerEvent) {
    measure.handlePointerCancel(e);
    gestures.handlePointerEnd(e);
  }

  function onModalTouchStart(e: TouchEvent) {
    measure.handleTouchStart(e);
    gestures.handleTouchStart(e);
  }

  function onModalTouchMove(e: TouchEvent) {
    measure.handleTouchMove(e);
    gestures.handleTouchMove(e);
  }

  function onModalTouchEnd(e: TouchEvent) {
    gestures.handleTouchEnd(e);
    measure.handleTouchEnd(e);
  }

  function onModalTouchCancel(e: TouchEvent) {
    measure.handleTouchCancel(e);
    gestures.handleTouchEnd(e);
  }

  // Scroll lock for the lightbox (Kata xy31): while the modal is open the
  // page behind it must never scroll. Two layers:
  //   1. refcounted overflow:hidden on <html>/<body> — kills document
  //      scrolling below lg (above lg the stylesheet already hides the root
  //      scroller);
  //   2. non-passive wheel/touchmove guards on the backdrop that
  //      preventDefault() every event landing OUTSIDE the modal's scrollable
  //      panel, so browser scroll chaining can never reach a container
  //      behind the overlay. The panel itself carries `overscroll-contain`
  //      so its own scrolling never chains past the modal.
  //
  // Bits' own lock must stay OFF (`preventScroll={false}` below): enabled
  // alongside this helper it double-writes <body> style, and its 24ms
  // delayed reset restores a snapshot taken after this lock had already
  // written — the page stays overflow:hidden after close (kata 1jfa).
  $effect(() => {
    if (!expanded) return;
    const backdrop = backdropRef;
    if (!backdrop) return;
    const detachGuard = attachBackdropScrollGuard(backdrop, modalPanelRef);
    const unlock = lockPageScroll(document);
    return () => {
      detachGuard();
      unlock();
    };
  });
</script>

<Dialog.Root bind:open={expanded}>
  <Dialog.Portal>
    <Dialog.Overlay
      bind:ref={backdropRef}
      class="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm"
    />
    <Dialog.Content
      bind:ref={modalPanelRef}
      preventScroll={false}
      onEscapeKeydown={(event) => { if (selection.mode !== "pan") { event.preventDefault(); selection.clear(); selection.setMode("pan"); } else if (terminalTool?.active) { event.preventDefault(); terminalTool.cancel(); } }}
      aria-label="Coil Preview — expanded"
      class="fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100vh-2rem)] w-[calc(100%-2rem)] max-w-7xl -translate-x-1/2 -translate-y-1/2 flex-col gap-3 overflow-y-auto overscroll-contain rounded-lg border border-slate-700 bg-slate-900 p-4 shadow-2xl"
    >
      <!-- Header row -->
      <div class="flex items-center justify-between flex-wrap gap-2">
        <Dialog.Title level={3} class="text-sm font-semibold text-slate-200">
          Coil Preview
        </Dialog.Title>
        <div class="flex items-center gap-3 flex-wrap">
          <span class="text-xs text-slate-400">
            {stats}
          </span>
          <Dialog.Close
            class="px-2 py-0.5 text-xs rounded bg-slate-800 border border-slate-700 text-slate-300 hover:text-emerald-300 hover:border-emerald-600 transition-colors"
            aria-label="Close coil preview"
            ><X size={16} aria-hidden="true" /></Dialog.Close
          >
        </div>
      </div>

      <div role="toolbar" aria-label="Coil preview tools" class="flex flex-wrap items-start gap-2 border-y border-slate-700 py-2">
        {#if importedGeometry && onGeometryChange}
          <CadSelectionToolbar tool={selection} geometry={importedGeometry} onActivate={activateSelection} />
        {:else if onStartSegmentEditing}
          <button type="button" onclick={prepareSegments} disabled={preparingSegments} class="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-300 disabled:opacity-40" title="Create editable geometry to select and reassign segments. Edits stop following the routing settings.">{preparingSegments ? "Preparing segments…" : "Edit segments"}</button>
        {/if}
        {#if selectionError}<p role="alert" class="text-xs text-rose-200">{selectionError}</p>{/if}
        <CoilPreviewMeasureToolbar {measure} onToggle={() => { selection.setMode("pan"); terminalTool?.cancel(); measure.toggleMode(); }} />
        {#if onSimplify}
          <div class="flex flex-wrap items-center gap-2">
            <button type="button" aria-label="Simplify lines" onclick={() => { selection.clear(); selection.setMode("pan"); onSimplify?.(); }} disabled={terminalTool?.active} class="icon-tool rounded border border-slate-700 bg-slate-800 text-slate-300 hover:text-emerald-300 disabled:opacity-40" title="Simplify lines: merge collinear lines in saved and exported geometry."><GitMerge size={16} aria-hidden="true" /></button>
            {#if onUndoSimplify}<button type="button" aria-label="Undo simplify" title="Undo line simplification." onclick={() => { selection.clear(); onUndoSimplify?.(); }} disabled={terminalTool?.active} class="icon-tool rounded border border-slate-700 text-slate-400 hover:text-slate-100 disabled:opacity-40"><Undo2 size={16} aria-hidden="true" /></button>{/if}
            <span role="status" class="text-xs text-slate-400">{simplifyNotice}</span>
            {#if terminalTool && onStartTerminals}
              <button type="button" aria-label="Set coil terminals" onclick={() => { selection.setMode("pan"); onStartTerminals?.(); }} aria-pressed={terminalTool.active} title="Set coil terminals: review open ends, change either endpoint, or flip IN and OUT." class="icon-tool rounded border border-slate-700 bg-slate-800 text-slate-300 hover:text-emerald-300"><Plug size={16} aria-hidden="true" /></button>
              {#if terminalTool.notice}<span role="status" class="text-xs text-slate-400">{terminalTool.notice}</span>{/if}
            {/if}
          </div>
        {/if}
      </div>

      <div class="viewer-layout">
      <div class="min-w-0 flex flex-col gap-3">
      <!-- Modal frame div owns the ARIA label (the canvas is the paint
           target; data-* attributes carry the introspection counters,
           mirroring the inline pair). All gestures delegate to the same
           utility instance. -->
      <div
        bind:this={modalFrameRef}
        class="relative w-full touch-none select-none {gestures.isPanning
          ? 'cursor-grabbing'
           : measure.mode || terminalTool?.active
            ? 'cursor-crosshair'
            : 'cursor-grab'}"
        role={terminalTool?.active ? "group" : "img"}
        aria-label="Coil preview — expanded"
        style="aspect-ratio: {W} / {H};"
        onpointerdown={onModalPointerDown}
        onpointermove={onModalPointerMove}
        onpointerup={onModalPointerUp}
        onpointercancel={onModalPointerCancel}
        onlostpointercapture={gestures.handleLostPointerCapture}
        ontouchstart={onModalTouchStart}
        ontouchmove={onModalTouchMove}
        ontouchend={onModalTouchEnd}
        ontouchcancel={onModalTouchCancel}
      >
        <canvas bind:this={modalCanvasRef} class="block h-full w-full"
        ></canvas>
        {#if importedGeometry}
          <CoilTerminalOverlay geometry={importedGeometry} tool={terminalTool} transform={worldTransform} panX={gestures.panX} panY={gestures.panY} width={W} height={H} isVisible={isTerminalVisible} />
          {#if onGeometryChange}
            <CadSelectionOverlay geometry={importedGeometry} tool={selection} transform={worldTransform} panX={gestures.panX} panY={gestures.panY} width={W} height={H} worldScale={1e-3} isVisible={isTerminalVisible} disabled={measure.mode || terminalTool?.active || view.oneSection} />
          {/if}
        {/if}
      </div>

      <!-- Zoom + reset view below the expanded canvas, same layout as the
           inline preview. -->
      <CoilPreviewControls
        zoomLabel={gestures.zoomLabel}
        canZoomIn={gestures.canZoomIn}
        canZoomOut={gestures.canZoomOut}
        onZoomIn={gestures.zoomIn}
        onZoomOut={gestures.zoomOut}
        onResetZoom={gestures.zoomReset}
        onResetView={gestures.resetView}
      />

      <!-- Mover position: same controls as the Design reflection on the
           shared MotionStore, so the slider lives next to the strip it
           moves inside the lightbox. -->
      <MoverPositionControls {config} {motion} showWaveform={view.showWaveform} />

      </div>
      <aside class="layers-panel" aria-label="Layers panel">
        {#if terminalTool?.active}<CoilTerminalPanel tool={terminalTool} />{/if}
        <h4 class="shrink-0 border-b border-slate-700 px-3 py-2 text-sm font-semibold text-slate-200">Layers</h4>
        <div class="layers-body p-3">
          <CoilPreviewVisibilityPanel
            {view} {uniquePhases} {uniqueLayers} {hasPolePitchData}
            {hasBandWidthData} {hasPoleRegionData} {poleRegionPhases}
          />
          {#if importedGeometry && Object.keys(importedGeometry.coil_terminals ?? {}).length}
            <section class="mt-4 border-t border-slate-700 pt-3" aria-label="Configured coil terminals">
              <h4 class="mb-2 text-xs font-semibold text-slate-300">Coil terminals</h4>
              {#each Object.entries(importedGeometry.coil_terminals ?? {}) as [coil, terminals] (coil)}
                <div class="mb-3 space-y-1 text-[11px] text-slate-400">
                  <p class="font-semibold text-slate-200">Coil {coil}</p>
                  <p>IN {terminalDescription(terminals.input)}</p>
                  <p>OUT {terminalDescription(terminals.output)}</p>
                  <div class="flex gap-3">
                    <button type="button" disabled={terminalTool?.active} onclick={() => { selection.setMode("pan"); onStartTerminals?.(coil); }} class="text-xs text-emerald-300 disabled:opacity-40" aria-label={`Edit coil ${coil} terminals`}>Edit terminals</button>
                    {#if onGeometryChange}<button type="button" disabled={terminalTool?.active} onclick={() => { if (importedGeometry) onGeometryChange?.(assignCadTerminals(importedGeometry, coil, { input: terminals.output, output: terminals.input })); }} class="text-xs text-emerald-300 disabled:opacity-40" aria-label={`Flip coil ${coil} terminals`} title="Swap this coil's IN and OUT terminals.">Flip</button>{/if}
                  </div>
                </div>
              {/each}
            </section>
          {/if}
        </div>
      </aside>
      </div>

    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>

<style>
  .icon-tool { display: inline-flex; align-items: center; justify-content: center; width: 2rem; height: 2rem; }
  .icon-tool[aria-pressed="true"] { border-color: #34d399; color: #6ee7b7; background: #064e3b; }
  .icon-tool:focus-visible { outline: 2px solid #34d399; outline-offset: 2px; }
  .viewer-layout { display: grid; grid-template-columns: minmax(0, 1fr) 15rem; gap: 1rem; align-items: stretch; }
  .layers-panel { contain: size; display: flex; flex-direction: column; min-height: 0; overflow-y: auto; overscroll-behavior: contain; border: 1px solid rgb(var(--slate-700)); border-radius: 6px; background: rgb(var(--slate-900)); }
  .layers-body { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; }
  @media (max-width: 640px) {
    .viewer-layout { grid-template-columns: minmax(0, 1fr); }
    .layers-panel { contain: none; max-height: 24rem; }
  }
</style>
