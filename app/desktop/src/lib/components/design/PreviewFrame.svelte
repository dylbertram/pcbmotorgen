<script lang="ts">
  import type { Snippet } from "svelte";
  import type { CoilPreviewGestures } from "../../utils/coilPreviewGestures.svelte";
  import type { CoilPreviewMeasure } from "../../utils/coilPreviewMeasure.svelte";

  let { frame = $bindable(), width = $bindable(760), height = $bindable(260),
    gestures, measure, label, interactive = false, aspectRatio, children, ondblclick }: {
    frame?: HTMLDivElement;
    width?: number;
    height?: number;
    gestures: CoilPreviewGestures;
    measure?: CoilPreviewMeasure;
    label: string;
    interactive?: boolean;
    aspectRatio?: number;
    children: Snippet;
    ondblclick?: () => void;
  } = $props();

  $effect(() => {
    if (!frame) return;
    const node = frame;
    node.addEventListener("wheel", gestures.handleWheel, { passive: false });
    return () => node.removeEventListener("wheel", gestures.handleWheel);
  });
</script>

<div bind:this={frame} bind:clientWidth={width} bind:clientHeight={height}
  class="relative min-h-0 w-full touch-none select-none overflow-hidden {aspectRatio ? '' : 'h-full'} {gestures.isPanning ? 'cursor-grabbing' : measure?.mode || interactive ? 'cursor-crosshair' : 'cursor-grab'}"
  role={interactive ? "group" : "img"} aria-label={label} style:aspect-ratio={aspectRatio}
  onpointerdown={(e) => { measure?.handlePointerDown(e); gestures.handlePointerDown(e); }}
  onpointermove={(e) => { measure?.handlePointerMove(e); gestures.handlePointerMove(e); }}
  onpointerup={(e) => { gestures.handlePointerEnd(e); measure?.handlePointerUp(e); }}
  onpointercancel={(e) => { measure?.handlePointerCancel(e); gestures.handlePointerEnd(e); }}
  onlostpointercapture={gestures.handleLostPointerCapture}
  ontouchstart={(e) => { measure?.handleTouchStart(e); gestures.handleTouchStart(e); }}
  ontouchmove={(e) => { measure?.handleTouchMove(e); gestures.handleTouchMove(e); }}
  ontouchend={(e) => { gestures.handleTouchEnd(e); measure?.handleTouchEnd(e); }}
  ontouchcancel={(e) => { measure?.handleTouchCancel(e); gestures.handleTouchEnd(e); }}
  {ondblclick}>
  {@render children()}
</div>
