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
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { MotionStore } from "../../stores/motion.svelte";
  import { Dialog } from "bits-ui";
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
            >×</Dialog.Close
          >
        </div>
      </div>

      <div role="toolbar" aria-label="Coil preview tools" class="border-y border-slate-700 py-2">
        <CoilPreviewMeasureToolbar {measure} />
        {#if onSimplify}
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <button type="button" onclick={onSimplify} class="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-300 hover:text-emerald-300" title="Merge collinear lines in saved and exported geometry">Simplify lines</button>
            {#if onUndoSimplify}<button type="button" onclick={onUndoSimplify} class="px-2 py-1 text-xs text-slate-400 hover:text-slate-100">Undo simplify</button>{/if}
            <span role="status" class="text-xs text-slate-400">{simplifyNotice}</span>
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
          : measure.mode
            ? 'cursor-crosshair'
            : 'cursor-grab'}"
        role="img"
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
      <MoverPositionControls {config} {motion} />

      </div>
      <aside class="layers-panel" aria-label="Layers panel">
        <h4 class="shrink-0 border-b border-slate-700 px-3 py-2 text-sm font-semibold text-slate-200">Layers</h4>
        <div class="layers-body p-3">
          <CoilPreviewVisibilityPanel
            {view} {uniquePhases} {uniqueLayers} {hasPolePitchData}
            {hasBandWidthData} {hasPoleRegionData} {poleRegionPhases}
          />
        </div>
      </aside>
      </div>

    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>

<style>
  .viewer-layout { display: grid; grid-template-columns: minmax(0, 1fr) 15rem; gap: 1rem; align-items: stretch; }
  .layers-panel { contain: size; display: flex; flex-direction: column; min-height: 0; border: 1px solid rgb(var(--slate-700)); border-radius: 6px; background: rgb(var(--slate-900)); }
  .layers-body { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; }
  @media (max-width: 640px) {
    .viewer-layout { grid-template-columns: minmax(0, 1fr); }
    .layers-panel { contain: none; max-height: 24rem; }
  }
</style>
