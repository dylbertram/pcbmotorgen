<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import { Bounds, OrbitControls } from "@threlte/extras";
  import { untrack } from "svelte";
  import type { OrthographicCamera } from "three";
  import type { CoilScene, CopperPath } from "../../coilScene";
  import { PHASE_COLORS } from "./coilPreviewCanvas";
  import CoilCopperBatch from "./CoilCopperBatch.svelte";

  let { scene, paths, vias, terminals, traceMode, reset, command, zScale }: {
    scene: CoilScene;
    paths: CopperPath[];
    vias: CoilScene["vias"];
    terminals: CoilScene["terminals"];
    traceMode: "traces" | "centerlines";
    reset: number;
    command: { id: number; zoom: number };
    zScale: number;
  } = $props();
  const { size, invalidate } = useThrelte();
  let camera = $state.raw<OrthographicCamera>();
  let zoom = $derived(Math.max(1, Math.min($size.width, $size.height) / 14));
  let batches = $derived(scene.nets.map((net, idx) => ({ net, color: PHASE_COLORS[idx % PHASE_COLORS.length], paths: paths.filter(p => p.net === net) })));

  // Button zoom is relative to the current camera, including wheel/pinch changes.
  $effect(() => {
    const { id, zoom: factor } = command;
    // Camera replacement/reset and resizing must not replay the last command.
    untrack(() => {
      if (!id || !camera) return;
      camera.zoom = Math.max(zoom / 20, Math.min(zoom * 50, camera.zoom * factor));
      camera.updateProjectionMatrix();
      invalidate();
    });
  });
</script>

{#key reset}
  <T.OrthographicCamera bind:ref={camera} makeDefault position={[12, 10, 14]} {zoom} near={0.01} far={1000}>
    <OrbitControls enableDamping minZoom={zoom / 20} maxZoom={zoom * 50} />
  </T.OrthographicCamera>
{/key}
<T.AmbientLight intensity={1.5} />
<T.DirectionalLight position={[5, 10, 8]} intensity={2} />

{#key scene}
<Bounds animate={false} margin={1.25}>
{#each batches as batch (batch.net)}
  <CoilCopperBatch paths={batch.paths} width={scene.width} color={batch.color} {zScale} centerlines={traceMode === "centerlines"} />
{/each}
<CoilCopperBatch paths={vias} width={scene.width * 1.6} color="#fbbf24" {zScale} />
{#each terminals as terminal (terminal.key)}
  <T.Mesh position={[terminal.point.x, terminal.point.y * zScale, terminal.point.z]}>
    <T.SphereGeometry args={[Math.max(scene.width, 0.045), 12, 8]} />
    <T.MeshBasicMaterial color="#34d399" />
  </T.Mesh>
{/each}
</Bounds>
{/key}
