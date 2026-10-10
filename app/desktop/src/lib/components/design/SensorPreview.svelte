<script lang="ts">
  import type { SensorStore } from "../../stores/sensor.svelte";
  import { fitWorldToView, type WorldTransform } from "../../chart";
  import { CoilPreviewGestures } from "../../utils/coilPreviewGestures.svelte";
  import { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import { PREVIEW_W, PREVIEW_H } from "./coilPreviewCanvas";
  import CoilPreviewControls from "./CoilPreviewControls.svelte";
  import LayerVisibilityControls from "./LayerVisibilityControls.svelte";
  import { Dialog } from "bits-ui";
  import { attachBackdropScrollGuard, lockPageScroll } from "../../utils/pageScrollLock";

  let { store }: { store: SensorStore } = $props();

  let geometry = $derived(store.geometry);
  let expanded = $state(false);
  let backdropRef = $state<HTMLDivElement | null>(null);

  $effect(() => {
    if (!expanded || !backdropRef) return;
    const detachGuard = attachBackdropScrollGuard(backdropRef, null);
    const unlock = lockPageScroll(document);
    return () => {
      detachGuard();
      unlock();
    };
  });
  const previewView = new CoilPreviewViewState();
  const previewLayers = [{ idx: 0 }, { idx: 1 }];
  let previewBounds = $derived.by(() => {
    if (!geometry) return { minX: -12, minY: -9, maxX: 132, maxY: 9 };
    const [minX, minY, maxX, maxY] = geometry.board_bounds_mm;
    const pad = Math.max(1, Math.max(maxX - minX, maxY - minY) * 0.025);
    return { minX: minX - pad, minY: minY - pad, maxX: maxX + pad, maxY: maxY + pad };
  });

  function worldTransformFor(zoom: number): WorldTransform {
    return fitWorldToView(previewBounds, PREVIEW_W, PREVIEW_H, 24, zoom);
  }
  const gestures = new CoilPreviewGestures({
    virtualW: PREVIEW_W,
    virtualH: PREVIEW_H,
    minZoom: 0.5,
    maxZoom: Infinity,
    zoomSteps: [0.5, 1, 1.5, 2, 3, 4, 6, 8, 10],
    getWorldTransform: worldTransformFor,
  });
  let worldTransform = $derived(worldTransformFor(gestures.zoom));

  function attachWheel(frame: HTMLDivElement) {
    frame.addEventListener("wheel", gestures.handleWheel, { passive: false });
    return () => frame.removeEventListener("wheel", gestures.handleWheel);
  }

  function colorFor(net: string): string {
    if (net === "CL1") return "#fbbf24";
    if (net === "CL2") return "#22d3ee";
    return "#c084fc";
  }
</script>

<section
  class="overflow-hidden rounded-lg border border-slate-700 bg-slate-800/40"
  aria-labelledby="sensor-preview-title"
>
  <div class="flex items-center justify-between gap-3 border-b border-slate-700 px-3 py-2">
    <div>
      <h2 id="sensor-preview-title" class="text-xs font-semibold uppercase tracking-wider text-slate-200">
        Induction sensor preview
      </h2>
      <p class="mt-0.5 text-[11px] text-slate-500">Top-down · F.Cu and B.Cu overlaid</p>
    </div>
    <div class="flex items-center gap-3">
    {#if store.loading}
      <span class="text-[11px] text-amber-300" role="status">Generating…</span>
    {:else if geometry}
      <span class="font-mono text-[11px] text-slate-400">
        {geometry.nets.reduce((n, net) => n + net.segments.length, 0)} tracks
      </span>
    {/if}
    <button
      type="button"
      aria-label="Expand sensor preview"
      aria-expanded={expanded}
      onclick={() => (expanded = true)}
      class="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 text-xs text-slate-300 hover:border-emerald-600 hover:text-emerald-300"
    >⤢</button>
    </div>
  </div>

  {#if store.error}
    <div class="m-3 rounded-md border border-rose-500/50 bg-rose-500/10 px-3 py-2 text-xs text-rose-200" role="alert">
      {store.error}
    </div>
  {/if}

  {#snippet previewContent()}
  <div
    {@attach attachWheel}
    class="relative w-full touch-none select-none overflow-hidden bg-slate-950/70 {gestures.isPanning ? 'cursor-grabbing' : 'cursor-grab'}"
    role="img"
    aria-label="Generated two-layer induction position sensor traces"
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
    ondblclick={() => (expanded = true)}
  >
  <svg
    class="block h-full w-full"
    viewBox={`0 0 ${PREVIEW_W} ${PREVIEW_H}`}
    preserveAspectRatio="xMidYMid meet"
    aria-hidden="true"
  >
    <title>Induction position sensor copper layout</title>
    {#if geometry}
      <g transform={`matrix(${worldTransform.s} 0 0 ${-worldTransform.s} ${worldTransform.tx + gestures.panX} ${worldTransform.ty + gestures.panY})`}>
      {#each geometry.nets as net (net.name)}
        <g fill="none" stroke={colorFor(net.name)} stroke-width={net.trace_width_mm} stroke-linecap="round" stroke-linejoin="round">
          {#each net.segments as segment, index (`${net.name}-${index}`)}
            {#if previewView.isLayerVisible(segment.layer)}
            <line
              x1={segment.start.x}
              y1={segment.start.y}
              x2={segment.end.x}
              y2={segment.end.y}
              opacity={segment.layer === 0 ? 0.95 : 0.58}
              stroke-dasharray={segment.layer === 1 ? "0.8 0.55" : undefined}
            />
            {/if}
          {/each}
        </g>
      {/each}
      {#each geometry.nets as net (net.name)}
        {#each net.vias as via, index (`${net.name}-via-${index}`)}
          <circle
            cx={via.position.x}
            cy={via.position.y}
            r={net.via_size_mm / 2}
            fill="#fbbf24"
            stroke="#0f172a"
            stroke-width={net.trace_width_mm * 0.25}
          />
          <circle
            cx={via.position.x}
            cy={via.position.y}
            r="0.1"
            fill="#020617"
            stroke="#0f172a"
            stroke-width={net.trace_width_mm * 0.2}
          />
        {/each}
      {/each}
      {#each geometry.terminal_markers as [net, terminal], index (`terminal-${index}`)}
        <circle
          cx={terminal.x}
          cy={terminal.y}
          r="0.38"
          fill="#0f172a"
          stroke={colorFor(net)}
          stroke-width="0.16"
        />
      {/each}
      </g>
    {:else if !store.error}
      <text x={PREVIEW_W / 2} y={PREVIEW_H / 2} text-anchor="middle" fill="#94a3b8" font-size="14">
        {store.loading ? "Generating sensor geometry…" : "Sensor geometry unavailable"}
      </text>
    {/if}
  </svg>
  </div>

  <div class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-700 px-3 py-2">
    <LayerVisibilityControls
      layers={previewLayers}
      isVisible={(layer) => previewView.isLayerVisible(layer)}
      onToggle={(layer) => previewView.toggleLayer(layer)}
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
    <p class="w-full text-[11px] text-slate-500">Drag to pan; pinch or ctrl-scroll to zoom. Layer 0: F.Cu · Layer 1: B.Cu.</p>
  </div>
  {/snippet}

  {@render previewContent()}

  <Dialog.Root bind:open={expanded}>
    <Dialog.Portal>
      <Dialog.Overlay bind:ref={backdropRef} class="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm" />
      <Dialog.Content
        preventScroll={false}
        aria-label="Sensor preview expanded"
        class="fixed inset-4 z-50 flex flex-col gap-3 overflow-y-auto overscroll-contain rounded-lg border border-slate-700 bg-slate-900 p-4 shadow-2xl"
      >
        <div class="flex items-center justify-between gap-3">
          <Dialog.Title level={3} class="text-sm font-semibold text-slate-200">Induction sensor preview</Dialog.Title>
          <Dialog.Close aria-label="Close sensor preview" class="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 text-xs text-slate-300">×</Dialog.Close>
        </div>
        {@render previewContent()}
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>

  <div class="flex flex-wrap gap-x-4 gap-y-1 border-t border-slate-700 px-3 py-2 text-[11px] text-slate-400">
    {#each [{ name: "CL1", label: "Cosine receiver" }, { name: "CL2", label: "Sine receiver" }, { name: "OSC", label: "Transmitter" }] as item (item.name)}
      {#if geometry?.nets.some((net) => net.name === item.name)}
        <span class="inline-flex items-center gap-1.5">
          <span class="h-2 w-2 rounded-full" style:background-color={colorFor(item.name)}></span>
          {item.label}
        </span>
      {/if}
    {/each}
    <span class="ml-auto">dashed: B.Cu · solid: F.Cu</span>
  </div>
</section>
