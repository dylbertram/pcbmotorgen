<!--
  Expanded motor preview. The frame, editing toolbar, overlays, terminal
  controls, and Layers popover are shared with CAD import. CoilPreview owns
  the canvas renderer, camera, measure state, and presentation state so the
  inline and expanded previews stay synchronized.

  Custom document and backdrop scroll locks remain authoritative. Bits UI's
  delayed body-style restoration conflicts with these locks, so its built-in
  preventScroll stays disabled. Escape first cancels an active edit command.
-->
<script lang="ts">
  import { X } from "@lucide/svelte";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { MotionStore } from "../../stores/motion.svelte";
  import { Dialog } from "bits-ui";
  import { onDestroy } from "svelte";
  import type { CadGeometry } from "../../types";
  import type { WorldTransform } from "../../chart";
  import type { CoilTerminalTool } from "../../utils/coilTerminalTool.svelte";
  import CoilTerminalPanel from "./CoilTerminalPanel.svelte";
  import CoilTerminalSummary from "./CoilTerminalSummary.svelte";
  import type { CoilPreviewGestures } from "../../utils/coilPreviewGestures.svelte";
  import type { CoilPreviewMeasure } from "../../utils/coilPreviewMeasure.svelte";
  import {
    attachBackdropScrollGuard,
    lockPageScroll,
  } from "../../utils/pageScrollLock";
  import CoilPreviewControls from "./CoilPreviewControls.svelte";
  import GeometryEditingToolbar from "./GeometryEditingToolbar.svelte";
  import GeometryEditingOverlay from "./GeometryEditingOverlay.svelte";
  import PreviewFrame from "./PreviewFrame.svelte";
  import PreviewMeasureOverlay from "./PreviewMeasureOverlay.svelte";
  import PreviewLayersPopover from "./PreviewLayersPopover.svelte";
  import MoverPositionControls from "./MoverPositionControls.svelte";
  import { PREVIEW_H, PREVIEW_W } from "./coilPreviewCanvas";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";

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
  onDestroy(() => terminalTool?.cancel());

  let backdropRef: HTMLDivElement | null = $state(null);
  let modalPanelRef: HTMLDivElement | null = $state(null);

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
      onEscapeKeydown={(event) => { if (terminalTool?.active) { event.preventDefault(); terminalTool.cancel(); } else if (selection.selected.length || selection.anchor) { event.preventDefault(); selection.clear(); } }}
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

      <GeometryEditingToolbar label="Coil preview tools" geometry={onGeometryChange ? importedGeometry : null}
        {selection} {measure} {terminalTool} {onSimplify} {onUndoSimplify} {simplifyNotice}
        onActivateSelection={activateSelection} onPrepareGeometry={onStartSegmentEditing} {onStartTerminals} />
      {#if terminalTool?.active}<CoilTerminalPanel tool={terminalTool} />{/if}

      <div class="min-w-0 flex flex-col gap-3">
      <!-- Modal frame div owns the ARIA label (the canvas is the paint
           target; data-* attributes carry the introspection counters,
           mirroring the inline pair). All gestures delegate to the same
           utility instance. -->
      <PreviewFrame bind:frame={modalFrameRef} {gestures} {measure} interactive={terminalTool?.active ?? false}
        label="Coil preview — expanded" aspectRatio={W / H}>
        <canvas bind:this={modalCanvasRef} class="block h-full w-full"
        ></canvas>
        {#if importedGeometry}
          <GeometryEditingOverlay geometry={importedGeometry} {selection} {terminalTool} transform={worldTransform} panX={gestures.panX} panY={gestures.panY} width={W} height={H} worldScale={1e-3} isVisible={isTerminalVisible} disabled={!onGeometryChange || measure.mode || view.oneSection} />
        {/if}
        <PreviewMeasureOverlay {measure} transform={worldTransform} panX={gestures.panX} panY={gestures.panY} width={W} height={H} />
      </PreviewFrame>

      <!-- Zoom + reset view below the expanded canvas, same layout as the
           inline preview. -->
      <div class="flex flex-wrap items-center justify-between gap-3">
      <PreviewLayersPopover {view} layers={importedGeometry ? importedGeometry.layer_z_mm.map((_, idx) => ({ idx })) : uniqueLayers} phases={importedGeometry ? [] : uniquePhases}
        coils={importedGeometry ? uniquePhases.map((phase) => ({ name: phase.name, colorIdx: phase.colorIdx })) : []}
        isCoilVisible={(name) => view.isPhaseVisible(uniquePhases.find((phase) => phase.name === name)?.idx ?? -1)}
        onToggleCoil={(name) => { const phase = uniquePhases.find((phase) => phase.name === name); if (phase) view.phaseVisibility[phase.idx] = !view.isPhaseVisible(phase.idx); }} showMotorControls={true}
        label="Coil preview layers" {hasPolePitchData} {hasBandWidthData} {hasPoleRegionData} {poleRegionPhases} />
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

      <!-- Mover position: same controls as the Design reflection on the
           shared MotionStore, so the slider lives next to the strip it
           moves inside the lightbox. -->
      <MoverPositionControls {config} {motion} showWaveform={view.showWaveform} />

      </div>
      {#if importedGeometry}
        <CoilTerminalSummary geometry={importedGeometry} tool={terminalTool} onEdit={(coil) => { selection.setMode("pan"); onStartTerminals?.(coil); }} {onGeometryChange} />
      {/if}

    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
