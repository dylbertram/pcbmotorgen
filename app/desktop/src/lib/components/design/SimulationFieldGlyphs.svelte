<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import { DoubleSide } from "three";
  import type { CoilScene } from "../../coilScene";
  import type { FieldPreview } from "../../types/simulationVisualization";
  import { fieldGlyphGeometry } from "../../visualizationGeometry";
  import { fieldLineGeometry, fieldSliceGeometry, type FieldStyle } from "../../simulationFieldGeometry";

  let { field, scene, zScale, opacity, style, sliceFraction }: { field: FieldPreview; scene: CoilScene; zScale: number; opacity: number; style: FieldStyle; sliceFraction: number } = $props();
  const { invalidate } = useThrelte();
  const geometry = $derived(style === "slice" ? null : style === "arrows" ? fieldGlyphGeometry(field, scene, zScale) : fieldLineGeometry(field, scene, zScale, sliceFraction));
  const slice = $derived(style === "slice" || style === "lines-slice" ? fieldSliceGeometry(field, scene, zScale, sliceFraction) : null);
  $effect(() => { const current = geometry, currentSlice = slice; invalidate(); return () => { current?.dispose(); currentSlice?.dispose(); }; });
</script>

{#if slice}
<T.Mesh geometry={slice} renderOrder={-1}>
  <T.MeshBasicMaterial vertexColors transparent opacity={opacity * .6} side={DoubleSide} depthWrite={false} />
</T.Mesh>
{/if}
{#if geometry}
<T.LineSegments {geometry}>
  <T.LineBasicMaterial vertexColors transparent {opacity} depthWrite={false} />
</T.LineSegments>
{/if}
