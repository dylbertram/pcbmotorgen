<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import { BufferGeometry, Float32BufferAttribute } from "three";
  import type { Vector3 } from "three";
  import { rectangularCopperGeometry } from "../../copperMesh";
  import { viaBarrelsGeometry, type CopperPad } from "../../viaCopperMesh";

  let { paths, width, color, centerlines = false, zScale = 1, thickness = .0035, barrels = false, contextPaths, pads = [], padDiameter = 0, plating = .0025 }: {
    paths: { points: Vector3[] }[];
    width: number;
    color: string;
    centerlines?: boolean;
    zScale?: number;
    thickness?: number;
    barrels?: boolean;
    contextPaths?: { points: Vector3[] }[];
    pads?: CopperPad[];
    padDiameter?: number;
    plating?: number;
  } = $props();
  const { invalidate } = useThrelte();

  // Magnify layer positions, not the copper's physical cross-section.
  let scaledPaths = $derived(paths.map(path => path.points.map(p => p.clone().setY(p.y * zScale))));

  // Batch by coil rather than creating a Svelte component/draw call per segment.
  let geometry = $derived.by(() => {
    if (centerlines) {
      const positions: number[] = [];
      for (const points of scaledPaths) for (let i = 1; i < points.length; i++) positions.push(...points[i - 1].toArray(), ...points[i].toArray());
      return new BufferGeometry().setAttribute("position", new Float32BufferAttribute(positions, 3));
    }
    if (!barrels) return rectangularCopperGeometry(paths, width, thickness, zScale, contextPaths ?? paths, pads, padDiameter);
    return viaBarrelsGeometry(paths, width, plating, zScale);
  });
  $effect(() => {
    const current = geometry;
    invalidate();
    return () => current?.dispose();
  });
</script>

{#if geometry}
  {#if centerlines}
    <T.LineSegments userData={{ measureable: true, copperLayerY: barrels ? undefined : paths[0]?.points[0]?.y }}>
      <T is={geometry} />
      <T.LineBasicMaterial {color} />
    </T.LineSegments>
  {:else}
    <T.Mesh userData={{ measureable: true, copperLayerY: barrels ? undefined : paths[0]?.points[0]?.y }}>
      <T is={geometry} />
      <T.MeshStandardMaterial {color} roughness={0.5} metalness={0.25} />
    </T.Mesh>
  {/if}
{/if}
