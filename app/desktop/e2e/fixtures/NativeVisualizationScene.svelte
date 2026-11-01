<script lang="ts">
  import { Canvas } from "@threlte/core";
  import CoilPreviewScene from "../../src/lib/components/design/CoilPreviewScene.svelte";
  import { buildCoilScene } from "../../src/lib/coilScene";
  import { mapCopperLoss } from "../../src/lib/visualizationGeometry";
  import type { CadGeometry } from "../../src/lib/types";
  import type { FieldPreview, CopperLossPreview } from "../../src/lib/types/simulationVisualization";

  // Test-only frozen native report renderer. No synthetic field generation,
  // re-identified IPC response, force calculation or live native UI claim.
  let { geometry, field, loss = null }: { geometry: CadGeometry; field: FieldPreview | null; loss?: CopperLossPreview | null } = $props();
  const scene = $derived(buildCoilScene(geometry)!);
  const heat = $derived(loss ? mapCopperLoss(geometry, loss, "linear") : null);
</script>

<div data-testid="frozen-native-visualization" style="position:fixed;inset:0;z-index:10000;background:#f4f7fc;color:#182439">
  <div style="height:520px">
    <Canvas renderMode="on-demand">
      <CoilPreviewScene {scene} paths={scene.paths} vias={scene.vias} terminals={[]} traceMode="traces" reset={0}
        command={{ id: 0, zoom: 1 }} {field} {heat} opacity={1} fieldStyle="lines-slice" sliceFraction={.5} sectionView={true} magnets={field?.magnets ?? []} />
    </Canvas>
  </div>
  <p style="margin:12px 24px">Actual saved-design {field?.method === "qualified-finite-copper-winding-xyz" ? "finite-copper winding-current samples, including declared return, no magnets" : field?.method === "routed-current-biot-savart-xyz" ? "routed coil-current estimate, external returns omitted, no magnets" : field?.method === "routed-current-plus-pm-xyz" ? "routed coil-current estimate plus analytical PM samples" : "native PM samples"}. Interpolated field lines and XZ magnitude slice in Tesla.</p>
  <p style="margin:12px 24px">Frozen native-data browser rendering check only. No magnetic-material response, thermal prediction or observed native WKWebView acceptance.</p>
</div>
