<script lang="ts">
  import { T } from "@threlte/core";
  import type { CoilScene } from "../../coilScene";
  import type { FieldPreview } from "../../types/simulationVisualization";
  import { physicalToScene } from "../../visualizationGeometry";
  let { magnets, scene, zScale }: { magnets: FieldPreview["magnets"]; scene: CoilScene; zScale: number } = $props();
</script>
{#each magnets as magnet, i (i)}
  {@const at = physicalToScene(magnet.center_m, scene, zScale)}
  <T.Mesh position={[at.x, at.y, at.z]} userData={{ measureable: true }}>
    <T.BoxGeometry args={[magnet.size_m[0] * 1000 * scene.scale, magnet.size_m[2] * 1000 * scene.scale * zScale, magnet.size_m[1] * 1000 * scene.scale]} />
    <T.MeshStandardMaterial color={magnet.positive_z ? "#e78955" : "#5484bd"} transparent opacity={.35} depthWrite={false} />
  </T.Mesh>
{/each}
