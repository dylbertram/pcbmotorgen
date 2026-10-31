<script lang="ts">
  import CoilPreview3DView from "../../src/lib/components/design/CoilPreview3DView.svelte";
  import { CoilPreviewViewState } from "../../src/lib/components/design/coilPreviewViewState.svelte";
  import type { CadGeometry } from "../../src/lib/types";
  import { SpatialMeasure } from "../../src/lib/spatialMeasure.svelte";

  const view = new CoilPreviewViewState();
  view.viewMode = "iso";
  const measure = new SpatialMeasure();
  const geometry:CadGeometry = {
    trace_width_mm:.2, layer_z_mm:[0,-.3],
    routing:{format_version:2,segments:[0,1].map(layer=>({start:{x:0,y:0},end:{x:1,y:0},layer,net:"A",is_active:true})),curves:[],
      vias:[{position:{x:0,y:0},from_layer:0,to_layer:1,net:"A"}]},
    coil_terminals:{A:{input:{position:{x:1,y:0},layer:0},output:{position:{x:1,y:0},layer:1}}},
  };
</script>

<div data-testid="physical-copper-detail" style="position:fixed;inset:0;z-index:10000">
  <CoilPreview3DView {geometry} pcbThicknessMm={.3} pcbStackup={{copper_mm:[.035,.07],dielectric_mm:[.195]}} viaSizeMm={{diameter:.4,drill:.2,plating:.025}} {view} {measure}/>
  <button type="button" style="position:absolute;right:12px;bottom:40px" onclick={()=>measure.mode=true}>Measure terminal centers</button>
</div>
