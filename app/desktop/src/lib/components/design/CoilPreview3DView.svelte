<script lang="ts">
  import { Canvas } from "@threlte/core";
  import type { CadGeometry } from "../../types";
  import { buildCoilScene } from "../../coilScene";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import CoilPreviewScene from "./CoilPreviewScene.svelte";
  import Slider from "../ui/Slider.svelte";

  let { geometry, view, isVisible = () => true, showTerminals = true }: {
    geometry: CadGeometry | null;
    view: CoilPreviewViewState;
    isVisible?: (coil: string, layer: number) => boolean;
    showTerminals?: boolean;
  } = $props();

  let scene = $derived(buildCoilScene(geometry));
  let paths = $derived(scene?.paths.filter(p => view.isLayerVisible(p.layer) && isVisible(p.net, p.layer)) ?? []);
  let vias = $derived(view.showVias ? scene?.vias.filter(v =>
    (view.isLayerVisible(v.from_layer) && isVisible(v.net, v.from_layer)) ||
    (view.isLayerVisible(v.to_layer) && isVisible(v.net, v.to_layer))) ?? [] : []);
  let terminals = $derived(showTerminals && view.showTerminals ? scene?.terminals.filter(t => view.isLayerVisible(t.layer) && isVisible(t.net, t.layer)) ?? [] : []);
  let reset = $state(0);
  let command = $state({ id: 0, zoom: 1 });
</script>

<div class="coil-3d relative h-full w-full bg-slate-950" role="img" aria-label="Coil preview — isometric"
  data-testid="coil-iso" data-layers={geometry?.layer_z_mm.filter((_, i) => view.isLayerVisible(i)).length ?? 0}
  data-segments={paths.length} data-vias={vias.length} data-terminals={terminals.length} data-trace-mode={view.traceMode} data-z-scale={view.zScale}>
  {#if scene}
    <svelte:boundary>
      <Canvas renderMode="on-demand">
        <CoilPreviewScene {scene} {paths} {vias} {terminals} {reset} {command} zScale={view.zScale} traceMode={view.traceMode} />
      </Canvas>
      {#snippet failed()}
        <div class="flex h-full items-center justify-center p-4 text-sm text-slate-400" role="status">
          3D rendering is unavailable. Switch to Top-down to view this geometry.
        </div>
      {/snippet}
    </svelte:boundary>
    <div class="absolute left-2 top-2 flex gap-1 rounded border border-slate-700 bg-slate-900/95 p-1" role="group" aria-label="3D camera controls">
      <button class="text-slate-300 hover:bg-slate-800 hover:text-emerald-300" type="button" aria-label="Zoom in 3D" onclick={() => command = { id: command.id + 1, zoom: 1.25 }}>+</button>
      <button class="text-slate-300 hover:bg-slate-800 hover:text-emerald-300" type="button" aria-label="Zoom out 3D" onclick={() => command = { id: command.id + 1, zoom: 0.8 }}>−</button>
      <button class="text-slate-300 hover:bg-slate-800 hover:text-emerald-300" type="button" onclick={() => reset++}>Reset 3D view</button>
    </div>
    <div class="z-height absolute bottom-8 left-2 top-12 flex w-12 flex-col items-center gap-2 rounded border border-slate-700 bg-slate-900/95 px-2 py-2" role="group" aria-label="Z height">
      <span class="z-label text-xs text-slate-400">Z</span>
      <Slider orientation="vertical" min={1} max={20} step={0.1} bind:value={view.zScale} ariaLabel="Z height scale" class="min-h-0 flex-1" />
      <output class="font-mono text-[10px] text-emerald-300" aria-label="Z height multiplier">{view.zScale}×</output>
    </div>
    <div class="pointer-events-none absolute bottom-2 left-16 right-12 text-[10px] text-slate-400">
      Drag to orbit · Right-drag to pan · Scroll or pinch to zoom · Z × {view.zScale}
    </div>
    <div class="pointer-events-none absolute right-12 top-2 text-right font-mono text-[10px] text-slate-400">
      {#each geometry?.layer_z_mm ?? [] as z, idx (idx)}
        {#if view.isLayerVisible(idx)}<div>L{idx + 1} · {z.toFixed(2)} mm</div>{/if}
      {/each}
    </div>
  {:else}
    <div class="flex h-full items-center justify-center text-sm text-slate-500">Awaiting coil generation…</div>
  {/if}
</div>

<style>
  .coil-3d { container-type: size; }
  @container (max-height: 180px) {
    .z-height { top: 2.75rem; bottom: 0.25rem; padding: 0.25rem; gap: 0.25rem; }
    .z-label { display: none; }
  }
  button { padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.75rem; }
  button:focus-visible { outline: 2px solid #10b981; }
</style>
