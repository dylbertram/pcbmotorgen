<script lang="ts">
  import { Canvas } from "@threlte/core";
  import type { CadGeometry } from "../../types";
  import { buildCoilScene } from "../../coilScene";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import CoilPreviewScene from "./CoilPreviewScene.svelte";
  import Slider from "../ui/Slider.svelte";
  import { untrack, onDestroy } from "svelte";
  import type { VisualizationInput, VisualizationMode, VisualizationRequest } from "../../types/simulationVisualization";
  import { SimulationVisualizationController, type VisualizationView } from "../../simulationVisualizationController";
  import { sampleSimulationVisualization } from "../../ipc/simulationVisualization";
  import { FIELD_PALETTE, HEAT_PALETTE, mapCopperLoss } from "../../visualizationGeometry";
  import type { FieldStyle } from "../../simulationFieldGeometry";

  let { geometry, view, isVisible = () => true, showTerminals = true, simulation = null }: {
    geometry: CadGeometry | null;
    view: CoilPreviewViewState;
    isVisible?: (coil: string, layer: number) => boolean;
    showTerminals?: boolean;
    simulation?: VisualizationInput | null;
  } = $props();

  let scene = $derived(buildCoilScene(geometry));
  let paths = $derived(scene?.paths.filter(p => view.isLayerVisible(p.layer) && isVisible(p.net, p.layer)) ?? []);
  let vias = $derived(view.showVias ? scene?.vias.filter(v =>
    (view.isLayerVisible(v.from_layer) && isVisible(v.net, v.from_layer)) ||
    (view.isLayerVisible(v.to_layer) && isVisible(v.net, v.to_layer))) ?? [] : []);
  let terminals = $derived(showTerminals && view.showTerminals ? scene?.terminals.filter(t => view.isLayerVisible(t.layer) && isVisible(t.net, t.layer)) ?? [] : []);
  let reset = $state(0);
  let command = $state({ id: 0, zoom: 1 });
  let mode = $state<VisualizationMode>("fields");
  let density = $state("sparse");
  let opacity = $state(.8);
  let fieldStyle = $state<FieldStyle>("lines-slice");
  let sliceFraction = $state(.5);
  let sectionView = $state(false);
  let settingsOpen = $state(false);
  let legendsOpen = $state(false);
  let visualization = $state<VisualizationView>({ phase: "idle", report: null, error: null });
  const controller = new SimulationVisualizationController(sampleSimulationVisualization, next => { visualization = next; });
  const field = $derived(simulation ? visualization.report?.field ?? null : null);
  const heatMapping = $derived.by(() => {
    const heat = simulation ? visualization.report?.heat : null;
    if (!heat || !geometry) return { values: null, power: null, error: null };
    try { return { values: mapCopperLoss(geometry, heat, "linear"), power: mapCopperLoss(geometry, heat), error: null }; }
    catch (error) { return { values: null, power: null, error: String(error) }; }
  });
  const maximumField = $derived(field ? Math.max(0, ...field.samples.map(p => p.magnitude_t)) : 0);
  const maximumHeat = $derived(heatMapping.values ? Math.max(0, ...heatMapping.values.values()) : 0);
  const visibleHeat = $derived(heatMapping.power ? [...paths, ...vias].reduce((sum, p) => sum + (heatMapping.power?.get(p.key) ?? 0), 0) : 0);

  $effect.pre(() => {
    // Immutable snapshots bind every physical/current/pose input. Opacity and
    // display-only Z scaling do not resample physics. Edits clear colors now.
    const input = simulation ? $state.snapshot(simulation) : null;
    const physical = geometry ? $state.snapshot(geometry) : null;
    const selected = mode, resolution = density;
    untrack(() => controller.invalidate());
    if (!input || !physical || selected === "off") return;
    const positions = [...physical.routing.segments.flatMap(s => [s.start, s.end]), ...physical.routing.curves.flatMap(c => [c.start, c.mid, c.end])];
    if (!positions.length) return;
    const xs = positions.map(p => p.x * .001), ys = positions.map(p => p.y * .001);
    // Include the actual mover and return-flux space, not just the copper
    // bounding box. These are new native observations, never extrapolation.
    const pitch = input.config.magnet_pitch_m;
    const magnetHalfWidth = input.config.magnet_width_m / 2;
    const magnetStart = input.moverPositionM - magnetHalfWidth;
    const magnetEnd = input.moverPositionM + (input.config.magnet_count - 1) * pitch + magnetHalfWidth;
    const request: VisualizationRequest = { request_id: crypto.randomUUID(), mover_position_m: input.moverPositionM,
      bounds_m: [[Math.min(...xs, magnetStart) - pitch * .6, Math.max(...xs, magnetEnd) + pitch * .6], [Math.min(...ys) - .001, Math.max(...ys) + .001],
        [Math.min(...physical.layer_z_mm) * .001 - pitch * .6, input.config.air_gap_m + input.config.magnet_height_m + pitch * .6]],
      counts: resolution === "fine" ? [28, 4, 18] : resolution === "dense" ? [20, 5, 7] : [12, 4, 5], phase_peak_a: input.config.max_current_a,
      fields: selected === "fields" || selected === "both", heat: selected === "heat" || selected === "both" };
    const timer = setTimeout(() => { void controller.sample(input, request); }, 150);
    return () => { clearTimeout(timer); controller.invalidate(); };
  });
  onDestroy(() => controller.invalidate());
</script>

<div class="coil-3d relative h-full w-full bg-slate-950" role="img" aria-label="Coil preview — isometric"
  data-testid="coil-iso" data-layers={geometry?.layer_z_mm.filter((_, i) => view.isLayerVisible(i)).length ?? 0}
  data-segments={paths.length} data-vias={vias.length} data-terminals={terminals.length} data-trace-mode={view.traceMode} data-z-scale={view.zScale}
  data-field-samples={field?.samples.length ?? 0} data-field-style={fieldStyle} data-field-slice={sliceFraction} data-heat-unit="W/m" data-settings-open={settingsOpen} data-legends-open={legendsOpen} data-heat-paths={heatMapping.values?.size ?? 0} data-visualization-state={visualization.phase}>
  {#if scene}
    <svelte:boundary>
      <Canvas renderMode="on-demand">
        <CoilPreviewScene {scene} {paths} {vias} {terminals} {reset} {command} zScale={view.zScale} traceMode={view.traceMode}
           {field} heat={heatMapping.values} {opacity} {fieldStyle} {sliceFraction} {sectionView} />
      </Canvas>
      {#snippet failed()}
        <div class="flex h-full items-center justify-center p-4 text-sm text-slate-400" role="status">
          3D rendering is unavailable. Switch to Top-down to view this geometry.
        </div>
      {/snippet}
    </svelte:boundary>
    <div class="absolute left-2 top-2 flex gap-1 rounded border border-slate-700 bg-slate-900/95 p-1" role="group" aria-label="3D camera controls">
      <button class="text-slate-300 hover:bg-slate-800 hover:text-emerald-300" type="button" aria-label="Zoom in 3D" onclick={() => command = { id: command.id + 1, zoom: 1.25 }}>+</button>
      <button class="text-slate-300 hover:bg-slate-800 hover:text-emerald-300" type="button" aria-label="Zoom out 3D" onclick={() => command = { id: command.id + 1, zoom: 0.8 }}>−</button>
      <button class="text-slate-300 hover:bg-slate-800 hover:text-emerald-300" type="button" onclick={() => reset++}>Reset 3D view</button>
    </div>
    {#if simulation}
      <div class="simulation-controls absolute left-16 right-3 top-12 rounded border border-slate-700 bg-slate-900/95 p-2 text-xs text-slate-300" role="group" aria-label="3D simulation overlays">
        <button type="button" class="compact-overlay-toggle" aria-expanded={settingsOpen} onclick={() => settingsOpen = !settingsOpen}>Field and loss settings</button>
        <div class="overlay-control-fields flex flex-wrap items-center gap-2">
        <label class="flex items-center gap-1">Show
          <select aria-label="3D simulation overlay" bind:value={mode} class="rounded border border-slate-600 bg-slate-800 px-1 py-1 text-slate-100">
            <option value="off">Off</option><option value="fields">Magnetic fields</option><option value="heat">Copper heat / loss</option><option value="both">Fields and heat</option>
          </select>
        </label>
        {#if mode === "fields" || mode === "both"}
          <label class="flex items-center gap-1">Field view <select aria-label="Field rendering style" bind:value={fieldStyle} class="rounded border border-slate-600 bg-slate-800 p-1"><option value="lines-slice">Lines + slice</option><option value="lines">Field lines</option><option value="slice">Magnitude slice</option><option value="arrows">Sample arrows</option></select></label>
          <button class="rounded border border-slate-600 text-slate-300 hover:bg-slate-800 hover:text-emerald-300" type="button" aria-pressed={sectionView} onclick={() => sectionView = !sectionView}>XZ field section</button>
          <label class="flex items-center gap-1">Samples <select aria-label="Field sample density" bind:value={density} class="rounded border border-slate-600 bg-slate-800 p-1"><option value="sparse">240</option><option value="dense">700</option><option value="fine">2016</option></select></label>
          <label class="flex items-center gap-1">Opacity <input aria-label="Field overlay opacity" type="range" min="0.15" max="1" step="0.05" bind:value={opacity} class="w-16 accent-emerald-400" /></label>
          {#if fieldStyle !== "arrows"}<label class="flex items-center gap-1">Y slice <input aria-label="Field slice position" type="range" min="0" max="1" step="0.05" bind:value={sliceFraction} class="w-16 accent-emerald-400" /><output>{Math.round(sliceFraction * 100)}%</output></label>{/if}
        {/if}
        </div>
      </div>
      {#if mode !== "off"}
        <div class="overlay-legends pointer-events-auto absolute bottom-8 left-16 right-3 flex flex-wrap gap-2 overflow-y-auto text-[10px]" aria-label="Simulation overlay legend">
          {#if visualization.phase === "loading"}<p role="status" class="rounded bg-slate-900/95 p-2 text-slate-300">Sampling the active design. Previous visualization cleared.</p>{/if}
          {#if visualization.error}<p role="status" class="rounded bg-slate-900/95 p-2 text-amber-200">{visualization.error}</p>{/if}
          {#if visualization.report?.heat_unavailable_reason || heatMapping.error}
            <p role="status" class="max-w-md rounded bg-slate-900/95 p-2 text-amber-200">Heat/loss unavailable: {heatMapping.error ?? visualization.report?.heat_unavailable_reason}</p>
          {/if}
          <div class="compact-overlay-toggle w-full rounded border border-slate-700 bg-slate-900/95 p-1 text-slate-300">
            <p>{mode === "heat" ? "Loss W/m, not temperature" : mode === "both" ? "PM-only field · Loss W/m, not temperature" : "PM-only field · |B| in T"}</p>
            <button type="button" aria-expanded={legendsOpen} onclick={() => legendsOpen = !legendsOpen}>Legends and model limits</button>
          </div>
          <div class="overlay-legends-body flex flex-wrap gap-2">
          {#if field}
            <div class="max-w-64 space-y-1 rounded border border-slate-700 bg-slate-900/95 p-2 text-slate-300" aria-label="Magnetic field legend">
              <p>PM field magnitude |B| · T</p><div class="h-1.5 rounded" style:background={`linear-gradient(to right, ${FIELD_PALETTE.join(",")})`}></div>
              <p class="flex justify-between font-mono"><span>0 T</span><span>{maximumField.toPrecision(3)} T</span></p>
              <p>{fieldStyle === "arrows" ? "Native XYZ sample arrows" : "Interpolated XYZ field lines / XZ slice"}</p>
              <details><summary class="cursor-pointer">PM-only model limits</summary><p>Analytical permanent magnets only. No winding or nonlinear material response. Lines follow the interpolated native vector grid and stop at magnets or the sampled boundary. Seed density is not flux density. Interpolation is a display approximation, not added physical resolution.</p></details>
            </div>
          {/if}
          {#if heatMapping.values && visualization.report?.heat}
            <div class="max-w-72 space-y-1 rounded border border-slate-700 bg-slate-900/95 p-2 text-slate-300" aria-label="Copper loss legend">
              <p>Copper loss per length · W/m</p><div class="h-1.5 rounded" style:background={`linear-gradient(to right, ${HEAT_PALETTE.join(",")})`}></div>
              <p class="flex justify-between font-mono"><span>0 W/m</span><span>{maximumHeat.toPrecision(3)} W/m</span></p>
              <p>Total {visualization.report.heat.total_loss_w.toPrecision(4)} W · Visible {visibleHeat.toPrecision(4)} W</p>
              <p>Cycle-average branch I²R · {visualization.report.heat.phase_peak_a} A peak / {visualization.report.heat.phase_rms_a.toPrecision(3)} A RMS per winding phase.</p>
              <details><summary class="cursor-pointer">Loss estimate, not a temperature map</summary><p>Colors use branch watts divided by native conductor length, including arc chords and via intervals. Bends do not resolve current crowding. Resistance at {visualization.report.heat.winding_temperature_c} °C. Grey copper has no mapped branch result. No predicted temperature or hot spots. Contact/finite-volume current and housing heating are not qualified here.</p></details>
            </div>
          {/if}
          </div>
        </div>
      {/if}
    {/if}
    <div class="z-height absolute bottom-8 left-2 top-12 flex w-12 flex-col items-center gap-2 rounded border border-slate-700 bg-slate-900/95 px-2 py-2" role="group" aria-label="Z height">
      <span class="z-label text-xs text-slate-400">Z</span>
      <Slider orientation="vertical" min={1} max={20} step={0.1} bind:value={view.zScale} ariaLabel="Z height scale" class="min-h-0 flex-1" />
      <output class="font-mono text-[10px] text-emerald-300" aria-label="Z height multiplier">{view.zScale}×</output>
    </div>
    <div class="pointer-events-none absolute bottom-2 left-16 right-12 text-[10px] text-slate-400">
      Drag to orbit · Right-drag to pan · Scroll or pinch to zoom · Z × {view.zScale}
    </div>
    <div class="layer-depths pointer-events-none absolute right-12 top-2 text-right font-mono text-[10px] text-slate-400">
      {#each geometry?.layer_z_mm ?? [] as z, idx (idx)}
        {#if view.isLayerVisible(idx)}<div>L{idx + 1} · {z.toFixed(2)} mm</div>{/if}
      {/each}
    </div>
  {:else}
    <div class="flex h-full items-center justify-center text-sm text-slate-500">Awaiting coil generation…</div>
  {/if}
</div>

<style>
  .coil-3d { container-type: size; }
  .overlay-legends { max-height: 40cqh; }
  .compact-overlay-toggle { display: none; }
  @container (max-width: 520px) {
    .compact-overlay-toggle { display: block; }
    .overlay-control-fields, .overlay-legends-body { display: none; }
    .coil-3d[data-settings-open="true"] .overlay-control-fields { display: flex; max-height: 50cqh; overflow-y: auto; padding-top: 0.5rem; }
    .coil-3d[data-legends-open="true"] .overlay-legends-body { display: flex; }
    .layer-depths { display: none; }
    .simulation-controls { padding: 0.25rem; }
  }
  @container (max-height: 180px) {
    .z-height { top: 2.75rem; bottom: 0.25rem; padding: 0.25rem; gap: 0.25rem; }
    .z-label { display: none; }
  }
  button { padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.75rem; }
  button:focus-visible { outline: 2px solid #10b981; }
</style>
