<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import { BufferGeometry, Raycaster, Vector2, type OrthographicCamera } from "three";
  import type { CoilScene } from "../../coilScene";
  import type { SpatialMeasure } from "../../spatialMeasure.svelte";
  import { physicalMmToScene, sceneToPhysicalMm } from "../../spatialMeasureGeometry";
  import { terminalMarkerPickRadius } from "../../terminalMarkers";
  let { scene, measure, zScale }: { scene: CoilScene; measure: SpatialMeasure; zScale: number } = $props();
  const { canvas, dom, scene: world, camera, invalidate } = useThrelte();
  const raycaster = new Raycaster();
  // Pointer bookkeeping is deliberately non-reactive; it never drives markup.
  const endpoints = $derived(measure.mode && measure.p1 ? [measure.p1, measure.p2 ?? measure.cursor].filter(p => p !== null).map(p => physicalMmToScene(p, scene, zScale)) : []);
  const line = $derived(new BufferGeometry().setFromPoints(endpoints));
  $effect(() => { const current = line; invalidate(); return () => current.dispose(); });
  $effect(() => {
    if (!measure.mode) return;
    const downs = new Map<number, { x: number; y: number }>();
    let multi = false;
    const pick = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      raycaster.params.Line.threshold = Math.max(scene.width / 2, .02);
      const cam = camera.current as OrthographicCamera;
      raycaster.params.Points.threshold = cam.isOrthographicCamera ? terminalMarkerPickRadius(cam, rect.height) : scene.width / 2;
      raycaster.setFromCamera(new Vector2(2 * (event.clientX - rect.left) / rect.width - 1, 1 - 2 * (event.clientY - rect.top) / rect.height), camera.current);
      world.updateMatrixWorld(true);
      const hits = raycaster.intersectObjects(world.children, true).filter(hit => {
        if (!hit.object.userData.measureable) return false;
        for (let o = hit.object; o; o = o.parent!) if (!o.visible) return false;
        return true;
      });
      // Terminal dots are screen-space annotations drawn over copper. Pick
      // their exact electrical center rather than the trace's nearer face.
      const hit = hits.find(hit => hit.object.userData.terminalPointsMm) ?? hits[0];
      if (!hit) return null;
      return hit.object.userData.terminalPointsMm?.[hit.index ?? -1] ?? hit.object.userData.physicalPoint
        ?? sceneToPhysicalMm(hit.point, scene, zScale, hit.object.userData.copperLayerY);
    };
    const down = (e: PointerEvent) => { if (e.button !== 0) return; downs.set(e.pointerId, { x: e.clientX, y: e.clientY }); if (downs.size > 1) multi = true; };
    const move = (e: PointerEvent) => { if (measure.p1 && !measure.p2 && !downs.size) measure.cursor = pick(e); };
    const up = (e: PointerEvent) => {
      const start = downs.get(e.pointerId); downs.delete(e.pointerId);
      if (!multi && start && Math.hypot(e.clientX - start.x, e.clientY - start.y) <= 6) { const point = pick(e); if (point) measure.pick(point); }
      if (!downs.size) multi = false;
    };
    const cancel = () => { downs.clear(); multi = false; };
    // OrbitControls captures the pointer on its wrapper. Listen there in the
    // capture phase so pointer-up is not lost when its target leaves the canvas.
    dom.addEventListener("pointerdown", down, true); dom.addEventListener("pointermove", move, true);
    dom.addEventListener("pointerup", up, true); dom.addEventListener("pointercancel", cancel, true);
    return () => { dom.removeEventListener("pointerdown", down, true); dom.removeEventListener("pointermove", move, true); dom.removeEventListener("pointerup", up, true); dom.removeEventListener("pointercancel", cancel, true); };
  });
</script>

{#if endpoints.length > 1}
  <T.Line renderOrder={1000}>
    <T is={line} /><T.LineBasicMaterial color="#f472b6" depthTest={false} />
  </T.Line>
{/if}
{#each endpoints as point, i (i)}
  <T.Mesh position={point.toArray()} renderOrder={1000}>
    <T.SphereGeometry args={[Math.max(scene.width / 2, .025), 10, 8]} />
    <T.MeshBasicMaterial color="#f472b6" depthTest={false} />
  </T.Mesh>
{/each}
