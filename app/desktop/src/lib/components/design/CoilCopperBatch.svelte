<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import { BufferGeometry, Float32BufferAttribute, CurvePath, LineCurve3, TubeGeometry } from "three";
  import type { Vector3 } from "three";
  import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
  import { rectangularCopperGeometry } from "../../copperMesh";

  let { paths, width, color, centerlines = false, zScale = 1, thickness = .0035, barrels = false, contextPaths }: {
    paths: { points: Vector3[] }[];
    width: number;
    color: string;
    centerlines?: boolean;
    zScale?: number;
    thickness?: number;
    barrels?: boolean;
    contextPaths?: { points: Vector3[] }[];
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
    if (!barrels) return rectangularCopperGeometry(paths, width, thickness, zScale, contextPaths ?? paths);
    const tubes: TubeGeometry[] = [];
    for (const points of scaledPaths) {
      const path = new CurvePath<Vector3>();
      for (let i = 1; i < points.length; i++) {
        if (points[i - 1].distanceToSquared(points[i]) > 1e-16) path.add(new LineCurve3(points[i - 1], points[i]));
      }
      if (path.curves.length) tubes.push(new TubeGeometry(path, Math.max(1, points.length - 1), width / 2, 6, false));
    }
    const merged = tubes.length ? mergeGeometries(tubes) : new BufferGeometry();
    for (const tube of tubes) tube.dispose();
    return merged;
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
