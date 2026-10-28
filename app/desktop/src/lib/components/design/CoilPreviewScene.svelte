<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import { OrbitControls } from "@threlte/extras";
  import { untrack, tick } from "svelte";
  import { Box3, Vector3, type Group, type OrthographicCamera } from "three";
  import type { OrbitControls as OrbitController } from "three/examples/jsm/controls/OrbitControls.js";
  import { fitCoilCamera } from "../../fitCoilCamera";
  import type { CoilScene, CopperPath } from "../../coilScene";
  import { PHASE_COLORS } from "./coilPreviewCanvas";
  import CoilCopperBatch from "./CoilCopperBatch.svelte";
  import SimulationFieldGlyphs from "./SimulationFieldGlyphs.svelte";
  import SimulationMagnets from "./SimulationMagnets.svelte";
  import type { FieldPreview } from "../../types/simulationVisualization";
  import { HEAT_PALETTE, heatColor } from "../../visualizationGeometry";
  import type { FieldStyle } from "../../simulationFieldGeometry";

  let { scene, paths, vias, terminals, traceMode, reset, command, zScale, field = null, heat = null, opacity = .8, fieldStyle = "lines-slice", sliceFraction = .5, sectionView = false, magnets = [] }: {
    scene: CoilScene;
    paths: CopperPath[];
    vias: CoilScene["vias"];
    terminals: CoilScene["terminals"];
    traceMode: "traces" | "centerlines";
    reset: number;
    command: { id: number; zoom: number };
    zScale: number;
    field?: FieldPreview | null;
    heat?: Map<string, number> | null;
    opacity?: number;
    fieldStyle?: FieldStyle;
    sliceFraction?: number;
    sectionView?: boolean;
    magnets?: FieldPreview["magnets"];
  } = $props();
  const { size, invalidate } = useThrelte();
  let camera = $state.raw<OrthographicCamera>();
  let zoom = $derived(Math.max(1, Math.min($size.width, $size.height) / 14));
  const maximumLoss = $derived(heat ? Math.max(0, ...heat.values()) : 0);
  let batches = $derived(heat ? [...HEAT_PALETTE, "#64748b"].map(color => ({ net: color, color,
    paths: paths.filter(p => (heat.has(p.key) ? heatColor(heat.get(p.key)!, maximumLoss) : "#64748b") === color) }))
    : scene.nets.map((net, idx) => ({ net, color: PHASE_COLORS[idx % PHASE_COLORS.length], paths: paths.filter(p => p.net === net) })));
  const viaBatches = $derived(heat ? [...HEAT_PALETTE, "#64748b"].map(color => ({ color,
    paths: vias.filter(p => (heat.has(p.key) ? heatColor(heat.get(p.key)!, maximumLoss) : "#64748b") === color) }))
    : [{ color: "#fbbf24", paths: vias }]);
  let content = $state.raw<Group>();
  let controls = $state.raw<OrbitController>();
  let fittedView = "";
  // One controller owns the camera. A separate Bounds controller retains old
  // angles and can silently restore isometric view after selecting XZ.
  $effect(() => {
    void scene; void zScale; void field;
    const viewKey = `${reset}:${sectionView}`, width = $size.width, height = $size.height;
    if (!camera || !controls || !content) return;
    let cancelled = false;
    void tick().then(() => {
      if (cancelled || !camera || !controls || !content) return;
      // Flush residual orbit damping before a programmatic view change.
      const damping = controls.enableDamping;
      controls.enableDamping = false; controls.update(); controls.enableDamping = damping;
      const direction = fittedView === viewKey ? camera.position.clone().sub(controls.target)
        : sectionView ? new Vector3(0, 0, 1) : new Vector3(12, 10, 14);
      content.updateWorldMatrix(true, true);
      const center = fitCoilCamera(camera, new Box3().setFromObject(content, true), width, height, direction);
      if (center) { controls.target.copy(center); controls.update(); fittedView = viewKey; invalidate(); }
    });
    return () => { cancelled = true; };
  });

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

  <T.OrthographicCamera bind:ref={camera} makeDefault position={[12, 10, 14]} {zoom} near={0.01} far={1000}>
    <OrbitControls bind:ref={controls} enableDamping minZoom={zoom / 20} maxZoom={zoom * 50} />
  </T.OrthographicCamera>
<T.AmbientLight intensity={1.5} />
<T.DirectionalLight position={[5, 10, 8]} intensity={2} />

{#key scene}
<T.Group bind:ref={content}>
{#each batches as batch (batch.net)}
  <CoilCopperBatch paths={batch.paths} width={scene.width} color={batch.color} {zScale} centerlines={traceMode === "centerlines"} />
{/each}
{#each viaBatches as batch (batch.color)}
  <CoilCopperBatch paths={batch.paths} width={scene.width * 1.6} color={batch.color} {zScale} />
{/each}
{#if field}<SimulationFieldGlyphs {field} {scene} {zScale} {opacity} style={fieldStyle} {sliceFraction} />{/if}
<SimulationMagnets {magnets} {scene} {zScale} />
{#each terminals as terminal (terminal.key)}
  <T.Mesh position={[terminal.point.x, terminal.point.y * zScale, terminal.point.z]}>
    <T.SphereGeometry args={[Math.max(scene.width, 0.045), 12, 8]} />
    <T.MeshBasicMaterial color="#34d399" />
  </T.Mesh>
{/each}
</T.Group>
{/key}
