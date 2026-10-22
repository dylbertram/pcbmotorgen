<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import type { CoilScene } from "../../coilScene";
  import type { FieldPreview } from "../../types/simulationVisualization";
  import { fieldGlyphGeometry, physicalToScene } from "../../visualizationGeometry";

  let { field, scene, zScale, opacity }: { field: FieldPreview; scene: CoilScene; zScale: number; opacity: number } = $props();
  const { invalidate } = useThrelte();
  const geometry = $derived(fieldGlyphGeometry(field, scene, zScale));
  $effect(() => { const current = geometry; invalidate(); return () => current.dispose(); });
</script>

<T.LineSegments {geometry}>
  <T.LineBasicMaterial vertexColors transparent {opacity} />
</T.LineSegments>
{#each field.magnets as magnet, i (i)}
  {@const at = physicalToScene(magnet.center_m, scene, zScale)}
  <T.Mesh position={[at.x, at.y, at.z]}>
    <T.BoxGeometry args={[magnet.size_m[0] * 1000 * scene.scale, magnet.size_m[2] * 1000 * scene.scale * zScale, magnet.size_m[1] * 1000 * scene.scale]} />
    <T.MeshStandardMaterial color={magnet.positive_z ? "#e78955" : "#5484bd"} transparent opacity={opacity * .35} depthWrite={false} />
  </T.Mesh>
{/each}
