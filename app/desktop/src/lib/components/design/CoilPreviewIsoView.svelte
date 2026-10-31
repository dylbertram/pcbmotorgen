<script lang="ts">
  import type { CadGeometry } from "../../types";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import type { VisualizationInput } from "../../types/simulationVisualization";
  import type { SpatialMeasure } from "../../spatialMeasure.svelte";
  import type { PcbStackupMm } from "../../pcbStackup";
  import type { TopCameraTransform } from "../../fitCoilCamera";

  let { geometry, pcbThicknessMm, pcbStackup = null, copperThicknessMm = { outer: .035, inner: .035 }, viaSizeMm = {diameter:.4,drill:.2}, view, isVisible = () => true, showTerminals = true, simulation = null, measure = null, topCamera = null, visibleCopperKeys = null, onRenderStatus }: {
    geometry: CadGeometry | null;
    pcbThicknessMm: number;
    pcbStackup?: PcbStackupMm | null;
    viaSizeMm?: {diameter:number;drill:number;plating?:number};
    topCamera?: TopCameraTransform | null;
    visibleCopperKeys?: Set<string> | null;
    onRenderStatus?: (available:boolean)=>void;
    copperThicknessMm?: { outer: number; inner: number };
    view: CoilPreviewViewState;
    isVisible?: (coil: string, layer: number) => boolean;
    showTerminals?: boolean;
    simulation?: VisualizationInput | null;
    measure?: SpatialMeasure | null;
  } = $props();

  // Load the shared renderer separately from the document-management bundle.
  const viewer = import("./CoilPreview3DView.svelte").catch(error => {
    onRenderStatus?.(false);
    throw error;
  });
</script>

{#await viewer}
  <div class="flex h-full items-center justify-center text-sm text-slate-400" role="status">Loading viewer…</div>
{:then { default: Viewer }}
  <Viewer {geometry} {pcbThicknessMm} {pcbStackup} {copperThicknessMm} {viaSizeMm} {view} {topCamera} {visibleCopperKeys} {onRenderStatus} {isVisible} {showTerminals} {simulation} {measure} />
{:catch}
  <div class="pointer-events-none absolute bottom-2 left-2 right-2 text-xs text-slate-400" role="status">Could not load the shared viewer. Top-down uses the 2D fallback.</div>
{/await}
