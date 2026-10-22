<script lang="ts">
  import { Canvas } from "@threlte/core";
  import CoilPreviewScene from "../../src/lib/components/design/CoilPreviewScene.svelte";
  import { buildCoilScene } from "../../src/lib/coilScene";
  import { mapCopperLoss } from "../../src/lib/visualizationGeometry";
  import type { CadGeometry } from "../../src/lib/types";
  import type { VisualizationReport } from "../../src/lib/types/simulationVisualization";

  // Test-only frozen native report renderer. No synthetic field generation,
  // re-identified IPC response, force calculation or live native UI claim.
  let { geometry, report }: { geometry: CadGeometry; report: VisualizationReport } = $props();
  const scene = $derived(buildCoilScene(geometry)!);
  const heat = $derived(report.heat ? mapCopperLoss(geometry, report.heat, "linear") : null);
</script>

<div data-testid="frozen-native-visualization" style="position:fixed;inset:0;z-index:10000;background:#f4f7fc;color:#182439">
  <div style="height:520px">
    <Canvas renderMode="on-demand">
      <CoilPreviewScene {scene} paths={scene.paths} vias={scene.vias} terminals={[]} traceMode="traces" reset={0}
        command={{ id: 0, zoom: 1 }} zScale={1} field={report.field} {heat} opacity={1} fieldStyle="lines-slice" sliceFraction={.5} sectionView={true} />
    </Canvas>
  </div>
  <p style="margin:12px 24px">Actual saved Case A native PM samples. Interpolated field lines and XZ magnitude slice in Tesla. Copper colors show W/m, not temperature.</p>
  <p style="margin:12px 24px">Frozen native-data browser rendering check only. No winding/material field response or observed native WKWebView acceptance.</p>
</div>
