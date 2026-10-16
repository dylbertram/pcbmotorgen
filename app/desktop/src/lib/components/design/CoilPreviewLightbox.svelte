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
  import { Dialog, DropdownMenu } from "bits-ui";
  import { onDestroy } from "svelte";
  import type { CadGeometry } from "../../types";
  import type { WorldTransform } from "../../chart";
  import type { CoilTerminalTool } from "../../utils/coilTerminalTool.svelte";
  import CoilTerminalOverlay from "./CoilTerminalOverlay.svelte";
  import PreviewLayerSlider from "./PreviewLayerSlider.svelte";
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
  import PreviewSideRail from "./PreviewSideRail.svelte";
  import MoverPositionControls from "./MoverPositionControls.svelte";
  import { PREVIEW_H, PREVIEW_W } from "./coilPreviewCanvas";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";
  import HoldingForceChart from "./HoldingForceChart.svelte";
  import { stripBoundsDomainMm } from "../../previewGeometry";

  let {
    expanded = $bindable(false),
    height = PREVIEW_H,
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
    terminalGeometry = null,
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
    height?: number;
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
    terminalGeometry?: CadGeometry | null;
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

  // Keep the virtual width shared with the inline card; height follows the
  // modal's aspect ratio so canvas, overlays and gestures stay aligned.
  const W = PREVIEW_W;
  const H = $derived(height);
  const moverBounds = $derived(stripBoundsDomainMm(config, motion));
  const selection = new CadSelectionTool({ getGeometry: () => importedGeometry, onChange: (geometry) => onGeometryChange?.(geometry) });
  function activateSelection() { terminalTool?.cancel(); measure.mode = false; view.oneSection = false; }
  onDestroy(() => terminalTool?.cancel());

  let backdropRef: HTMLDivElement | null = $state(null);
  let modalPanelRef: HTMLDivElement | null = $state(null);
  // Height of the floating top toolbar, so the right rail can start under it
  // instead of reaching the modal's top edge.
  let toolbarHeight = $state(0);
  let terminalPanelOpen = $derived(view.terminalPanelOpen);

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
      class="fixed inset-x-6 bottom-6 top-12 z-50 flex flex-col overflow-hidden overscroll-contain rounded-lg border border-slate-700 bg-transparent shadow-2xl"
    >
      <!-- Header row -->
      <header class="z-30 flex shrink-0 items-center justify-between gap-2 border-b border-slate-700 bg-slate-900 px-3 py-2">
        <Dialog.Title level={3} class="text-sm font-semibold text-slate-200">
          Coil Preview
        </Dialog.Title>
        <div class="flex items-center gap-3 flex-wrap">
          <span class="hidden text-xs text-slate-400 sm:inline">
            {stats}
          </span>
          <Dialog.Close
            class="px-2 py-0.5 text-xs rounded bg-slate-800 border border-slate-700 text-slate-300 hover:text-emerald-300 hover:border-emerald-600 transition-colors"
            aria-label="Close coil preview"
            ><X size={16} aria-hidden="true" /></Dialog.Close
          >
        </div>
      </header>

      <!-- Workspace: the drawing fills it and every dock sits flush inside it,
           so the toolbar meets the header and the rail has no top or bottom gap. -->
      <div class="relative min-h-0 flex-1">
        <!-- Modal frame div owns the ARIA label (the canvas is the paint
             target; data-* attributes carry the introspection counters,
             mirroring the inline pair). All gestures delegate to the same
             utility instance. -->
        <div class="absolute inset-0">
          <PreviewFrame bind:frame={modalFrameRef} {gestures} {measure} interactive={terminalTool?.active ?? false}
            label="Coil preview — expanded">
            <canvas bind:this={modalCanvasRef} class="block h-full w-full"
            ></canvas>
            {#if importedGeometry}
              <GeometryEditingOverlay geometry={importedGeometry} {selection} {terminalTool} renderTerminals={!terminalGeometry} showTerminals={view.showTerminals} markerRightInset={terminalPanelOpen ? 284 : 44} transform={worldTransform} panX={gestures.panX} panY={gestures.panY} width={W} height={H} worldScale={1e-3} isVisible={isTerminalVisible} disabled={!onGeometryChange || measure.mode || view.oneSection} />
            {/if}
            {#if terminalGeometry}
              <CoilTerminalOverlay geometry={terminalGeometry} tool={terminalTool} transform={worldTransform} panX={gestures.panX} panY={gestures.panY} width={W} height={H} worldScale={1e-3} isVisible={isTerminalVisible} showMarkers={view.showTerminals} rightInset={terminalPanelOpen ? 284 : 44} />
            {/if}
            <PreviewMeasureOverlay {measure} transform={worldTransform} panX={gestures.panX} panY={gestures.panY} width={W} height={H} />
          </PreviewFrame>
        </div>

        <!-- The toolbar spans the workspace top, flush under the header and
             backed so the buttons stay legible over the drawing. -->
        <div class="absolute inset-x-0 top-0 z-20" bind:clientHeight={toolbarHeight}>
          <GeometryEditingToolbar label="Coil preview tools" geometry={onGeometryChange ? importedGeometry : null}
            {selection} {measure} {terminalTool} {onSimplify} {onUndoSimplify} {simplifyNotice} borderless
            onActivateSelection={activateSelection} onPrepareGeometry={onStartSegmentEditing} />
        </div>

        <!-- Right rail: hangs from the bottom of the top toolbar down to the
             status bar, so the Layers and Display panels pull out under it. -->
        <div class="absolute bottom-0 right-0 z-20 w-11" style:top={`${toolbarHeight}px`}>
          <PreviewSideRail {view} layers={importedGeometry ? importedGeometry.layer_z_mm.map((_, idx) => ({ idx })) : uniqueLayers} phases={importedGeometry ? [] : uniquePhases}
            {terminalTool} {onStartTerminals} terminalsDisabled={!onGeometryChange}
           geometry={terminalGeometry ?? importedGeometry} selection={importedGeometry ? selection : undefined} assignmentDisabled={!importedGeometry || !onGeometryChange || measure.mode || !!terminalTool?.active || view.oneSection}
          coils={importedGeometry ? uniquePhases.map((phase) => ({ name: phase.name, colorIdx: phase.colorIdx })) : []}
          isCoilVisible={(name) => view.isPhaseVisible(uniquePhases.find((phase) => phase.name === name)?.idx ?? -1)}
          onToggleCoil={(name) => { const phase = uniquePhases.find((phase) => phase.name === name); if (phase) view.phaseVisibility[phase.idx] = !view.isPhaseVisible(phase.idx); }} showMotorControls={true}
            label="Coil preview layers" displayLabel="Coil preview display" {hasPolePitchData} {hasBandWidthData} {hasPoleRegionData} {poleRegionPhases} dismissOnOutsideClick={false} />
        </div>

        <!-- Bare zoom buttons: no background, with the same 12px gap on the
             right as the position box has at the bottom. -->
        <div class="absolute z-20 top-[32%] sm:top-auto sm:bottom-3 {terminalPanelOpen ? 'hidden sm:block' : ''}" style:right={terminalPanelOpen ? "calc(15rem + 3.5rem)" : "3.5rem"}>
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
             moves inside the lightbox. The phase-waveform popover is anchored
             directly above this box at the same width, so it cannot be moved. -->
        <div class="absolute bottom-3 left-2 z-20 flex w-[min(420px,calc(100%-4rem))] flex-col gap-2">
          {#if terminalPanelOpen}
            <div class="rounded-md border border-slate-700 bg-slate-900/95 p-3">
              <PreviewLayerSlider {view} layers={importedGeometry ? importedGeometry.layer_z_mm.map((_, idx) => ({ idx })) : uniqueLayers} onSelect={(layer) => { if (layer !== null && terminalTool?.active) terminalTool.chooseLayer(layer); view.phaseVisibility = []; }} />
            </div>
          {:else}
          {#if view.showWaveform}
            <div role="dialog" aria-label="Phase waveform"
              class="relative">
              <button type="button" aria-label="Close phase waveform"
                class="absolute right-1 top-1 z-10 rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                onclick={() => { view.showWaveform = false; }}><X size={16} aria-hidden="true" /></button>
              <HoldingForceChart {config} {motion} flush />
            </div>
          {/if}
          <div class="rounded-md border border-slate-700 bg-slate-900/95 p-3">
            <MoverPositionControls {config} {motion} showWaveform={false} compact />
          </div>
          {/if}
        </div>
      </div>

      <div class="z-30 flex shrink-0 items-center justify-between gap-3 border-t border-slate-700 bg-slate-900 px-3 py-2 text-[10px] text-slate-400" role="group" aria-label="Preview status">
        <span class="min-w-0 flex-1 font-mono">Position: {motion.clampedPositionMm.toFixed(1)} mm · Mover extent: {moverBounds.startMm.toFixed(1)} – {moverBounds.endMm.toFixed(1)} mm</span>
        <DropdownMenu.Root>
          <DropdownMenu.Trigger class="shrink-0 rounded border border-slate-700 px-2 py-1 text-xs hover:text-emerald-300" aria-label="Display state">Display ▾</DropdownMenu.Trigger>
          <DropdownMenu.Portal><DropdownMenu.Content preventScroll={false} class="z-[150] rounded border border-slate-700 bg-slate-900 p-1 text-xs text-slate-200" side="top" sideOffset={8}>
            <DropdownMenu.CheckboxItem bind:checked={view.showWaveform} class="cursor-default rounded px-3 py-2 outline-none data-[highlighted]:bg-slate-800">{view.showWaveform ? "✓ " : ""}Show phase waveform</DropdownMenu.CheckboxItem>
          </DropdownMenu.Content></DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>

    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
