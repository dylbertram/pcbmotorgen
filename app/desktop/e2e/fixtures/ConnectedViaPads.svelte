<script lang="ts">
  import CoilPreview3DView from "../../src/lib/components/design/CoilPreview3DView.svelte";
  import ViewportViewControls from "../../src/lib/components/design/ViewportViewControls.svelte";
  import { CoilPreviewViewState } from "../../src/lib/components/design/coilPreviewViewState.svelte";
  import type { CadGeometry } from "../../src/lib/types";

  const view = new CoilPreviewViewState();
  view.viewMode = "iso";
  const geometry: CadGeometry = {
    trace_width_mm: .2, layer_z_mm: [0, -.16, -.32, -.48, -.64, -.8],
    routing: { format_version: 2,
      segments: [0, 2, 5].map((layer, i) => ({ start: { x: 0, y: 0 }, end: { x: i === 1 ? -1 : 1, y: i === 2 ? 1 : 0 }, layer, net: "A", is_active: true })),
      curves: [], vias: [{ position: { x: 0, y: 0 }, from_layer: 0, to_layer: 5, net: "A" }],
    },
  };
  let hideBranch = $state(false);
  const visibleCopperKeys = $derived(hideBranch ? new Set(["segment-0", "segment-2"]) : null);
</script>

<div data-testid="connected-via-pads" style="position:fixed;inset:0;z-index:10000">
  <CoilPreview3DView {geometry} pcbThicknessMm={.8} viaSizeMm={{ diameter: .4, drill: .2, plating: .025 }} {view} {visibleCopperKeys} />
  <div style="position:absolute;top:8px;left:64px"><ViewportViewControls {view} /></div>
  <div style="position:absolute;bottom:8px;right:8px" class="bg-slate-900 p-2 text-slate-200">
    <label><input type="checkbox" bind:checked={hideBranch} />Hide branch connection</label>
    {#each geometry.layer_z_mm as _, layer (layer)}
      <label><input type="checkbox" checked={view.isLayerVisible(layer)} onchange={() => view.toggleLayer(layer)} aria-label={`Show layer ${layer + 1}`} />L{layer + 1}</label>
    {/each}
  </div>
</div>
