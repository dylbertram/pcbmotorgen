<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import { BufferGeometry } from "three";
  import { onDestroy } from "svelte";
  import type { CoilScene } from "../../coilScene";
  import { sceneToPhysicalMm } from "../../spatialMeasureGeometry";
  import { TERMINAL_MARKER_SIZE_PX, terminalMarkerTexture } from "../../terminalMarkers";

  let { terminals, scene, zScale }: { terminals:CoilScene["terminals"];scene:CoilScene;zScale:number } = $props();
  const { invalidate } = useThrelte();
  const texture = terminalMarkerTexture();
  const geometry = $derived(new BufferGeometry().setFromPoints(terminals.map(t => t.point.clone().setY(t.point.y * zScale))));
  const physicalPoints = $derived(terminals.map(t => sceneToPhysicalMm(t.point, scene, 1)));
  $effect(() => { const current = geometry; invalidate(); return () => current.dispose(); });
  onDestroy(() => texture.dispose());
</script>

<T.Points renderOrder={1000} frustumCulled={false} userData={{measureable:true,terminalPointsMm:physicalPoints}}>
  <T is={geometry}/>
  <T.PointsMaterial color="#34d399" size={TERMINAL_MARKER_SIZE_PX} sizeAttenuation={false} map={texture} transparent alphaTest={.05} depthTest={false} depthWrite={false} toneMapped={false}/>
</T.Points>
