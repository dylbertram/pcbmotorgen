<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import { Bounds, OrbitControls } from "@threlte/extras";
  import { untrack, tick } from "svelte";
  import type { OrthographicCamera } from "three";
  import type { CoilScene, CopperPath } from "../../coilScene";
  import { PHASE_COLORS } from "./coilPreviewCanvas";
  import CoilCopperBatch from "./CoilCopperBatch.svelte";
  import SimulationFieldGlyphs from "./SimulationFieldGlyphs.svelte";
  import type { FieldPreview } from "../../types/simulationVisualization";
  import { HEAT_PALETTE, heatColor } from "../../visualizationGeometry";
  import type { FieldStyle } from "../../simulationFieldGeometry";

  let { scene, paths, vias, terminals, traceMode, reset, command, zScale, field = null, heat = null, opacity = .8, fieldStyle = "lines-slice", sliceFraction = .5, sectionView = false }: {
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
  let bounds = $state<Bounds>();
  // Fit new field extents and display-only Z exaggeration after geometry mounts.
  $effect(() => {
    void scene; void zScale; void reset; void field; void sectionView;
    let cancelled = false;
    void tick().then(() => { if (!cancelled) bounds?.fit(); });
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

{#key `${reset}:${sectionView}`}
  <T.OrthographicCamera bind:ref={camera} makeDefault position={sectionView ? [0, 0, 14] : [12, 10, 14]} {zoom} near={0.01} far={1000}>
    <OrbitControls enableDamping minZoom={zoom / 20} maxZoom={zoom * 50} />
  </T.OrthographicCamera>
{/key}
<T.AmbientLight intensity={1.5} />
<T.DirectionalLight position={[5, 10, 8]} intensity={2} />

{#key scene}
<Bounds bind:this={bounds} animate={false} margin={1.25}>
{#each batches as batch (batch.net)}
  <CoilCopperBatch paths={batch.paths} width={scene.width} color={batch.color} {zScale} centerlines={traceMode === "centerlines"} />
{/each}
{#each viaBatches as batch (batch.color)}
  <CoilCopperBatch paths={batch.paths} width={scene.width * 1.6} color={batch.color} {zScale} />
{/each}
{#if field}<SimulationFieldGlyphs {field} {scene} {zScale} {opacity} style={fieldStyle} {sliceFraction} />{/if}
{#each terminals as terminal (terminal.key)}
  <T.Mesh position={[terminal.point.x, terminal.point.y * zScale, terminal.point.z]}>
    <T.SphereGeometry args={[Math.max(scene.width, 0.045), 12, 8]} />
    <T.MeshBasicMaterial color="#34d399" />
  </T.Mesh>
{/each}
</Bounds>
{/key}
