<script lang="ts">
  import { Minus, Plus, RotateCcw } from "@lucide/svelte";
  import ZoomWindowIcon from "./ZoomWindowIcon.svelte";
  /** Presentation-only controls; gesture and camera state stay with the caller. */
  let {
    zoomLabel,
    zoomInDisabled,
    zoomOutDisabled,
    onZoomIn,
    onZoomOut,
    onResetZoom,
    onResetView,
    onToggleZoomWindow,
    zoomWindow = false,
  }: {
    zoomLabel: string;
    zoomInDisabled: boolean;
    zoomOutDisabled: boolean;
    onZoomIn: () => void;
    onZoomOut: () => void;
    onResetZoom: () => void;
    onResetView: () => void;
    onToggleZoomWindow?: () => void;
    zoomWindow?: boolean;
  } = $props();
</script>

<div class="flex items-center justify-end gap-1" role="group" aria-label="Zoom controls">
  <button
    type="button"
    class="px-2 py-0.5 text-xs rounded bg-slate-800 border border-slate-700 text-slate-300 hover:text-emerald-300 hover:border-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
    aria-label="Zoom out"
    title="Zoom out"
    disabled={zoomOutDisabled}
    onclick={onZoomOut}
  ><Minus size={16} aria-hidden="true" /></button>
  <button
    type="button"
    class="px-2 py-0.5 text-xs font-mono rounded bg-slate-800 border border-slate-700 text-slate-300 hover:text-emerald-300 hover:border-emerald-600 transition-colors"
    aria-label="Reset zoom"
    title="Reset zoom"
    onclick={onResetZoom}
  >{zoomLabel}×</button>
  <button
    type="button"
    class="px-2 py-0.5 text-xs rounded bg-slate-800 border border-slate-700 text-slate-300 hover:text-emerald-300 hover:border-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
    aria-label="Zoom in"
    title="Zoom in"
    disabled={zoomInDisabled}
    onclick={onZoomIn}
  ><Plus size={16} aria-hidden="true" /></button>
  {#if onToggleZoomWindow}
    <button type="button" class="nav-action" aria-label="Zoom window" aria-pressed={zoomWindow}
      title="Zoom window: drag a rectangle or click two opposite corners. Escape cancels." onclick={onToggleZoomWindow}><ZoomWindowIcon /></button>
  {/if}
  <button
    type="button"
    class="ml-1 px-2 py-0.5 text-xs rounded bg-slate-800 border border-slate-700 text-slate-300 hover:text-emerald-300 hover:border-emerald-600 transition-colors"
    aria-label="Reset view"
    title="Reset view"
    onclick={onResetView}
   ><RotateCcw size={16} aria-hidden="true" /></button>
</div>

<style>
  button { display: inline-flex; align-items: center; justify-content: center; min-width: 2rem; min-height: 2rem; }
  button:focus-visible { outline: 2px solid #34d399; outline-offset: 2px; }
  .nav-action { border: 1px solid rgb(var(--slate-700)); border-radius: .25rem; background: rgb(var(--slate-800)); color: rgb(var(--slate-300)); }
  .nav-action:hover, .nav-action[aria-pressed="true"] { color: rgb(var(--emerald-300)); border-color: rgb(var(--emerald-600)); }
</style>
