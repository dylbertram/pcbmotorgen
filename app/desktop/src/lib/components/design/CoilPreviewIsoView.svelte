<script lang="ts">
  import type { CadGeometry } from "../../types";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";

  let { geometry, view, isVisible = () => true, showTerminals = true }: {
    geometry: CadGeometry | null;
    view: CoilPreviewViewState;
    isVisible?: (coil: string, layer: number) => boolean;
    showTerminals?: boolean;
  } = $props();

  // Keep Three.js and Threlte out of the initial, top-down app bundle.
  const viewer = import("./CoilPreview3DView.svelte");
</script>

{#await viewer}
  <div class="flex h-full items-center justify-center text-sm text-slate-400" role="status">Loading 3D viewer…</div>
{:then { default: Viewer }}
  <Viewer {geometry} {view} {isVisible} {showTerminals} />
{:catch}
  <div class="flex h-full items-center justify-center text-sm text-slate-400" role="status">Could not load the 3D viewer. Switch to Top-down to view this geometry.</div>
{/await}
