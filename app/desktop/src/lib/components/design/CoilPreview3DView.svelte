<script lang="ts">
  import { Canvas } from "@threlte/core";
  import type { CadGeometry } from "../../types";
  import { buildCoilScene, connectedViaPads, isViaVisible } from "../../coilScene";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import CoilPreviewScene from "./CoilPreviewScene.svelte";
  import Slider from "../ui/Slider.svelte";
  import { untrack, onDestroy } from "svelte";
  import type { VisualizationInput, VisualizationMode, VisualizationRequest } from "../../types/simulationVisualization";
  import { SimulationVisualizationController, type VisualizationView } from "../../simulationVisualizationController";
  import { sampleSimulationVisualization } from "../../ipc/simulationVisualization";
  import { FIELD_PALETTE, HEAT_PALETTE, mapCopperLoss } from "../../visualizationGeometry";
  import type { FieldStyle } from "../../simulationFieldGeometry";
  import type { DcWindingFieldResult } from "../../types/dcCoupling";
  import QualifiedCoilFieldControls from "./QualifiedCoilFieldControls.svelte";
  import { combineVisualizationFields } from "../../combineVisualizationFields";
  import { placedCopperGeometry } from "../../copperLayerPlacement";
  import { pcbBody } from "../../pcbBody";
  import type { SpatialMeasure } from "../../spatialMeasure.svelte";
  import ZoomWindowOverlay from "./ZoomWindowOverlay.svelte";
  import type { PcbStackupMm } from "../../pcbStackup";
  import type { TopCameraTransform } from "../../fitCoilCamera";
  import ViewportAxes from "./ViewportAxes.svelte";

  let { geometry: sourceGeometry, pcbThicknessMm, pcbStackup = null, copperThicknessMm = { outer: .035, inner: .035 }, viaSizeMm = {diameter:.4,drill:.2}, view, isVisible = () => true, showTerminals = true, simulation = null, measure = null, topCamera = null, visibleCopperKeys = null, onRenderStatus, axisRightInset = 0 }: {
    geometry: CadGeometry | null;
    pcbThicknessMm: number;
    pcbStackup?: PcbStackupMm | null;
    viaSizeMm?: {diameter:number;drill:number;plating?:number};
    topCamera?: TopCameraTransform | null;
    visibleCopperKeys?: Set<string> | null;
    onRenderStatus?: (available:boolean)=>void;
    axisRightInset?: number;
    copperThicknessMm?: { outer: number; inner: number };
    view: CoilPreviewViewState;
    isVisible?: (coil: string, layer: number) => boolean;
    showTerminals?: boolean;
    simulation?: VisualizationInput | null;
    measure?: SpatialMeasure | null;
  } = $props();

  const placement = $derived.by(() => {
    try { return { geometry: sourceGeometry ? placedCopperGeometry(sourceGeometry, pcbThicknessMm, pcbStackup) : null, error: "" }; }
    catch (error) { return { geometry: null, error: error instanceof Error ? error.message : String(error) }; }
  });
  const geometry = $derived(placement.geometry);
  let scene = $derived(buildCoilScene(geometry, { ...copperThicknessMm, layers: pcbStackup?.copper_mm }));
  const board = $derived(geometry && scene ? pcbBody(geometry, scene, pcbThicknessMm, view.zScale, pcbStackup ? 0 : undefined) : null);
  $effect(() => { void geometry; untrack(() => measure?.clear()); });
  let paths = $derived(scene?.paths.filter(p => view.isLayerVisible(p.layer) && isVisible(p.net, p.layer) && (!visibleCopperKeys || visibleCopperKeys.has(p.key))) ?? []);
  let vias = $derived(view.showVias ? scene?.vias.filter(v =>
    isViaVisible(v, layer => view.isLayerVisible(layer), isVisible)) ?? [] : []);
  const pads = $derived(scene ? connectedViaPads(scene, paths, viaSizeMm.diameter * scene.scale) : []);
  let terminals = $derived(showTerminals && view.showTerminals ? scene?.terminals.filter(t => view.isLayerVisible(t.layer) && isVisible(t.net, t.layer)) ?? [] : []);
  let windowCommand = $state<{ id: number; a: [number, number]; b: [number, number] }>({ id: 0, a: [0, 0], b: [1, 1] });
  let cameraSnapshot = $state<{ position: number[]; target: number[]; up: number[]; zoom: number } | null>(null);
  let glAvailable = $state<boolean | null>(null);
  let mode = $state<VisualizationMode>("fields");
  let density = $state("sparse");
  let opacity = $state(.8);
  let fieldStyle = $state<FieldStyle>("lines-slice");
  let sliceFraction = $state(.5);
  let sectionView = $state(false);
  let settingsOpen = $state<boolean | null>(null);
  let viewerWidth = $state(0);
  const settingsExpanded = $derived(settingsOpen ?? viewerWidth > 760);
  let legendsOpen = $state(false);
  let fieldSource = $state("coils");
  let phaseAngle = $state(0);
  let sampleRevision = $state(0);
  let coilField = $state<DcWindingFieldResult | null>(null);
  let showMagnets = $state(true);
  let includeMagnets = $state(false);
  let magnetContribution = $state<VisualizationView>({ phase: "idle", report: null, error: null });
  const magnetController = new SimulationVisualizationController(sampleSimulationVisualization, next => { magnetContribution = next; });
  let visualization = $state<VisualizationView>({ phase: "idle", report: null, error: null });
  const controller = new SimulationVisualizationController(sampleSimulationVisualization, next => { visualization = next; });
  const field = $derived.by(() => {
    if (!simulation || view.viewMode === "top") return null;
    if (mode !== "fields" && mode !== "both") return null;
    if (fieldSource === "coils") return visualization.report?.field ?? null;
    if (fieldSource === "pm") return includeMagnets ? visualization.report?.field ?? null : null;
    if (!coilField) return null;
    if (!includeMagnets) return coilField.field;
    const pm = magnetContribution.report?.field;
    return pm ? combineVisualizationFields(coilField.field, pm) : null;
  });
  // Visible solids are independent of the selected field and its availability.
  const visibleMagnets = $derived(simulation && showMagnets && view.viewMode !== "top" ? Array.from({ length: simulation.config.magnet_count }, (_, i) => ({
    center_m: [simulation.moverPositionM + i * simulation.config.magnet_pitch_m, simulation.config.board_width_m / 2,
      simulation.config.air_gap_m + simulation.config.magnet_height_m / 2] as [number, number, number],
    size_m: [simulation.config.magnet_width_m, simulation.config.magnet_cross_width_m, simulation.config.magnet_height_m] as [number, number, number], positive_z: i % 2 === 0,
  })) : []);
  const heatMapping = $derived.by(() => {
    const heat = simulation ? visualization.report?.heat : null;
    if (!heat || !geometry) return { values: null, power: null, error: null };
    try { return { values: mapCopperLoss(geometry, heat, "linear"), power: mapCopperLoss(geometry, heat), error: null }; }
    catch (error) { return { values: null, power: null, error: String(error) }; }
  });
  const maximumField = $derived(field ? Math.max(0, ...field.samples.map(p => p.magnitude_t)) : 0);
  const sliceYmm = $derived.by(() => {
    if (!field) return null;
    const ys = field.samples.map(p => p.position_m[1]), low = Math.min(...ys), high = Math.max(...ys);
    return (low + sliceFraction * (high - low)) * 1000;
  });
  const fieldDescription = $derived(fieldStyle === "arrows" ? "Native XYZ sample arrows"
    : fieldStyle === "lines-3d" ? "3D trajectories through interpolated XYZ samples"
    : fieldStyle === "slice" ? "XZ slice colored by full |B|"
    : "XZ-projected Bx/Bz lines; color shows full |B|");
  const maximumHeat = $derived(heatMapping.values ? Math.max(0, ...heatMapping.values.values()) : 0);
  const visibleHeat = $derived(heatMapping.power ? [...paths, ...vias].reduce((sum, p) => sum + (heatMapping.power?.get(p.key) ?? 0), 0) : 0);

  $effect.pre(() => {
    // Immutable snapshots bind every physical/current/pose input. Opacity and
    // display-only Z scaling do not resample physics. Edits clear colors now.
    const input = simulation ? $state.snapshot(simulation) : null;
    const physical = geometry ? $state.snapshot(geometry) : null;
    const selected = mode, resolution = density, source = fieldSource, pmEnabled = includeMagnets, angle = phaseAngle;
    void sampleRevision;
    untrack(() => controller.invalidate());
    if (!input || !physical || selected === "off") return;
    if (source === "coils" && selected !== "heat" && !Number.isFinite(angle)) {
      untrack(() => { visualization = { phase: "failed", report: null, error: "Enter a finite electrical angle in degrees." }; });
      return;
    }
    if (source === "qualified" && selected === "fields") return;
    if (source === "pm" && !pmEnabled && selected === "fields") return;
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
      field_source: source === "coils" ? pmEnabled ? "coils-and-pm" : "coils" : "pm", phase_angle_deg: source === "coils" && selected !== "heat" ? angle : 0,
      fields: (source === "coils" || (source === "pm" && pmEnabled)) && (selected === "fields" || selected === "both"), heat: selected === "heat" || selected === "both" };
    const timer = setTimeout(() => { void controller.sample(input, request); }, 150);
    return () => { clearTimeout(timer); controller.invalidate(); };
  });
  $effect.pre(() => {
    const input = simulation ? $state.snapshot(simulation) : null;
    const coil = coilField ? $state.snapshot(coilField) : null;
    const enabled = includeMagnets && fieldSource === "qualified" && (mode === "fields" || mode === "both");
    untrack(() => magnetController.invalidate());
    if (!enabled || !input || !coil) return;
    const request: VisualizationRequest = { request_id: crypto.randomUUID(), mover_position_m: input.moverPositionM,
      ...coil.sampling, phase_peak_a: input.config.max_current_a, fields: true, heat: false };
    void magnetController.sample(input, request);
    return () => magnetController.invalidate();
  });
  onDestroy(() => { controller.invalidate(); magnetController.invalidate(); });
</script>

<div class="coil-3d relative h-full w-full bg-slate-900" bind:clientWidth={viewerWidth} role="img" aria-label={`Coil preview — ${view.viewMode}`}
  data-testid={`coil-${view.viewMode}`} data-renderer={glAvailable === false ? "canvas2d-fallback" : "shared-three"} data-layers={geometry?.layer_z_mm.filter((_, i) => view.isLayerVisible(i)).length ?? 0}
  data-layer-z-mm={JSON.stringify(geometry?.layer_z_mm ?? [])} data-pcb-thickness-mm={pcbThicknessMm}
  data-trace-width-mm={scene ? scene.width / scene.scale : 0} data-trace-width-px={view.traceMode === "centerlines" ? 1 : (scene?.width ?? 0) * (cameraSnapshot?.zoom ?? 0)} data-via-diameter-mm={viaSizeMm.diameter} data-via-drill-mm={viaSizeMm.drill}
  data-segments={paths.length} data-vias={vias.length} data-via-pads={vias.length ? pads.length : 0} data-terminals={terminals.length} data-trace-mode={view.traceMode} data-z-scale={view.zScale} data-pcb-visible={view.showPcb} data-copper-section="rectangular" data-measure-points={measure?.p2 ? 2 : measure?.p1 ? 1 : 0} data-measure-mm={measure?.distanceMm ?? ""} data-camera={cameraSnapshot ? JSON.stringify(cameraSnapshot) : ""}
  data-field-samples={field?.samples.length ?? 0} data-visible-magnets={visibleMagnets.length} data-include-magnets={includeMagnets} data-field-source={fieldSource} data-field-style={fieldStyle} data-field-slice={sliceFraction} data-heat-unit="W/m" data-settings-open={settingsExpanded} data-legends-open={legendsOpen} data-heat-paths={heatMapping.values?.size ?? 0} data-visualization-state={visualization.phase}>
  {#if scene}
    <svelte:boundary onerror={() => { glAvailable=false; onRenderStatus?.(false); }}>
      <Canvas renderMode="on-demand">
         <CoilPreviewScene {scene} {paths} {vias} {pads} viaSize={{diameter:viaSizeMm.diameter*scene.scale,drill:viaSizeMm.drill*scene.scale,plating:(viaSizeMm.plating ?? .025)*scene.scale}} {terminals} reset={view.cameraReset} fit={view.cameraFit} command={view.cameraCommand} {windowCommand} {board} {measure} {topCamera} viewMode={view.viewMode} onCamera={snapshot => {cameraSnapshot = snapshot; if(view.viewMode !== "top") view.spatialZoom=snapshot.zoom/snapshot.fitZoom; glAvailable=true; onRenderStatus?.(true);}} showPcb={view.showPcb} zScale={view.zScale} traceMode={view.traceMode}
           {field} heat={heatMapping.values} {opacity} {fieldStyle} {sliceFraction} {sectionView} magnets={visibleMagnets} />
      </Canvas>
      {#snippet failed()}
        <div class="pointer-events-none absolute bottom-2 left-2 right-2 text-xs text-slate-400" role="status">
          {view.viewMode === "top" ? "WebGL unavailable. Using the 2D fallback." : "3D rendering is unavailable. Switch to Top-down to view this geometry."}
        </div>
      {/snippet}
    </svelte:boundary>
    <div class="axis-indicator pointer-events-none absolute z-10" style:right={`calc(.75rem + ${axisRightInset}px)`}>
      <ViewportAxes view={view.viewMode} camera={glAvailable === false ? null : cameraSnapshot} />
    </div>
    {#if view.zoomWindow && view.viewMode !== "top"}
      <ZoomWindowOverlay onCancel={() => view.zoomWindow = false} onFit={(a, b) => { windowCommand = { id: windowCommand.id + 1, a, b }; view.zoomWindow = false; }} />
    {/if}
    {#if view.viewMode !== "top"}
    {#if simulation}
      <div class="simulation-controls absolute right-2 top-2 z-20 rounded border border-slate-700 bg-slate-900/95 text-xs text-slate-300" role="group" aria-label="3D simulation overlays">
        <button type="button" class="inspector-toggle" aria-expanded={settingsExpanded} onclick={() => settingsOpen = !settingsExpanded}>
          <span>Field and loss settings</span><span aria-hidden="true">{settingsExpanded ? "−" : "+"}</span>
        </button>
        <div class="overlay-control-fields" hidden={!settingsExpanded}>
        <label class="control-row"><span>Overlay</span>
          <select aria-label="3D simulation overlay" bind:value={mode} class="rounded border border-slate-600 bg-slate-800 px-1 py-1 text-slate-100">
            <option value="off">Off</option><option value="fields">Magnetic fields</option><option value="heat">Copper heat / loss</option><option value="both">Fields and heat</option>
          </select>
        </label>
        <label class="check-row"><input type="checkbox" aria-label="Show magnets in 3D" bind:checked={showMagnets} /> <span>Show magnets in 3D</span></label>
        {#if mode === "fields" || mode === "both"}
          <fieldset class="control-section"><legend>Source</legend>
            <label class="control-row"><span>Calculate B</span><select aria-label="Magnetic field source" bind:value={fieldSource} onchange={event => { if (event.currentTarget.value === "pm") includeMagnets = true; }} class="rounded border border-slate-600 bg-slate-800 p-1"><option value="coils">Coil currents, routed estimate</option><option value="qualified">Coil currents, audited finite copper</option><option value="pm">Permanent magnets only</option></select></label>
            <label class="check-row"><input type="checkbox" aria-label="Include magnets in B-field" bind:checked={includeMagnets} /> <span>Include magnets in B-field</span></label>
            {#if fieldSource !== "qualified"}<label class="control-row"><span>Native samples</span><select aria-label="Field sample density" bind:value={density} class="rounded border border-slate-600 bg-slate-800 p-1"><option value="sparse">240</option><option value="dense">700</option><option value="fine">2016</option></select></label>
              {#if fieldSource === "coils"}
                <label class="control-row"><span>Electrical angle (°)</span><input aria-label="Coil field electrical angle" type="number" min="-360" max="360" step="15" bind:value={phaseAngle} class="min-w-0 rounded border border-slate-600 bg-slate-800 p-1" /></label>
                <p class="control-hint">Active copper at {simulation.config.max_current_a} A phase peak. Sorted phase nets use cos(θ − 360° k/N), input to output. External leads and return wiring omitted. Estimate, not audited FEM.</p>
              {/if}
              <button type="button" disabled={visualization.phase === "loading"} onclick={() => sampleRevision++} class="section-button rounded border border-emerald-600 text-emerald-200 disabled:opacity-40">Sample active geometry</button>
            {/if}
          </fieldset>
          <fieldset class="control-section"><legend>Display</legend>
            <label class="control-row"><span>Rendering</span><select aria-label="Field rendering style" bind:value={fieldStyle} class="rounded border border-slate-600 bg-slate-800 p-1"><option value="lines-slice">Projected lines + slice</option><option value="lines">Projected lines</option><option value="slice">Magnitude slice</option><option value="lines-3d">3D field lines</option><option value="arrows">3D sample arrows</option></select></label>
            <p class="control-hint">{fieldDescription}. Display interpolation only.</p>
            {#if fieldStyle !== "arrows"}
              <label class="range-control"><span>{fieldStyle === "lines-3d" ? "Seed plane Y" : "Slice Y"}</span><output aria-label="Field slice readout">{sliceYmm === null ? `${Math.round(sliceFraction * 100)}%` : `${sliceYmm.toFixed(2)} mm`}</output>
                <input aria-label="Field slice position" aria-valuetext={sliceYmm === null ? `${Math.round(sliceFraction * 100)}%` : `${sliceYmm.toFixed(2)} millimeters, ${Math.round(sliceFraction * 100)}%`} type="range" min="0" max="1" step="0.01" bind:value={sliceFraction} class="accent-emerald-400" />
              </label>
            {/if}
            <label class="range-control"><span>Opacity</span><output>{Math.round(opacity * 100)}%</output><input aria-label="Field overlay opacity" type="range" min="0.15" max="1" step="0.05" bind:value={opacity} class="accent-emerald-400" /></label>
            <button class="section-button rounded border border-slate-600 text-slate-300 hover:bg-slate-800 hover:text-emerald-300" type="button" aria-pressed={sectionView} onclick={() => sectionView = !sectionView}>XZ field section</button>
          </fieldset>
          {#if fieldSource === "qualified" && geometry}
            <details open={!coilField} class="basis-full"><summary class="cursor-pointer">Qualified coil source and DC drive</summary>
              <QualifiedCoilFieldControls input={simulation} {geometry} active={true} onResult={value => { coilField = value; }} />
            </details>
          {/if}
        {/if}
        </div>
      </div>
      {#if mode !== "off"}
        <div class="overlay-legends pointer-events-auto absolute bottom-8 left-16 right-3 flex flex-wrap gap-2 overflow-y-auto text-[10px]" aria-label="Simulation overlay legend">
          {#if visualization.phase === "loading"}<p role="status" class="rounded bg-slate-900/95 p-2 text-slate-300">Sampling the active design. Previous visualization cleared.</p>{/if}
          {#if visualization.error}<p role="status" class="rounded bg-slate-900/95 p-2 text-amber-200">{visualization.error}</p>{/if}
          {#if magnetContribution.phase === "loading"}<p role="status" class="rounded bg-slate-900/95 p-2 text-slate-300">Sampling magnet contribution on the coil observation grid. Combined field cleared.</p>{/if}
          {#if magnetContribution.error}<p role="status" class="rounded bg-slate-900/95 p-2 text-amber-200">Combined field unavailable: {magnetContribution.error}</p>{/if}
          {#if fieldSource === "pm" && !includeMagnets}<p role="status" class="rounded bg-slate-900/95 p-2 text-slate-300">Magnets excluded from calculation. No active field source.</p>{/if}
          {#if fieldSource === "qualified" && (mode === "fields" || mode === "both") && !coilField}<p role="status" class="rounded bg-slate-900/95 p-2 text-slate-300">Audited finite-copper fields require an exact qualified source and its declared return. For other designs choose "Coil currents, routed estimate" in field settings.</p>{/if}
          {#if visualization.report?.heat_unavailable_reason || heatMapping.error}
            <p role="status" class="max-w-md rounded bg-slate-900/95 p-2 text-amber-200">Heat/loss unavailable: {heatMapping.error ?? visualization.report?.heat_unavailable_reason}</p>
          {/if}
          <div class="compact-overlay-toggle w-full rounded border border-slate-700 bg-slate-900/95 p-1 text-slate-300">
            <p>{mode === "heat" ? "Loss W/m, not temperature" : `${fieldSource !== "pm" ? includeMagnets ? "Coils + PM, free-space sum" : fieldSource === "coils" ? "Routed coil estimate" : "Audited DC coil-current" : "PM-only"} field · |B| in T${mode === "both" ? " · Loss W/m" : ""}`}</p>
            <button type="button" aria-expanded={legendsOpen} onclick={() => legendsOpen = !legendsOpen}>Legends and model limits</button>
          </div>
          <div class="overlay-legends-body flex flex-wrap gap-2">
          {#if field}
            <div class="max-w-64 space-y-1 rounded border border-slate-700 bg-slate-900/95 p-2 text-slate-300" aria-label="Magnetic field legend">
              <p>{fieldSource !== "pm" ? includeMagnets ? "Coils + magnets, free-space sum" : "Coil-current" : "PM"} field magnitude |B| · T</p><div class="h-1.5 rounded" style:background={`linear-gradient(to right, ${FIELD_PALETTE.join(",")})`}></div>
              <p class="flex justify-between font-mono"><span>0 T</span><span>{maximumField.toPrecision(3)} T</span></p>
              <p>{fieldDescription}</p>
              {#if fieldSource === "coils"}
                <p>Routed-current estimate, {simulation.config.max_current_a} A phase peak, {phaseAngle}° electrical.</p>
                <details><summary class="cursor-pointer">Routed-current model limits</summary><p>Biot-Savart contribution from active routed traces, arc chords and vias, using signed resistor-graph branch currents. Softened filament core radius is half the actual trace width. External leads, terminal buses and return wiring are omitted, so this is not the complete drive-loop field. No magnetic-material response, audited FEM accuracy or holding-force prediction. {includeMagnets ? "Analytical PM vectors added in free space." : "No magnet contribution."}</p></details>
              {:else if fieldSource === "qualified"}
                {#if includeMagnets}<p>Vector superposition of native coil and PM samples at identical XYZ points. No magnetic-material reaction or coupled FEM solution.</p>{/if}
                <p>{coilField?.loop_current_a} A audited DC loop, including declared finite return. {Object.entries(coilField?.phase_currents_a ?? {}).map(([net, amps]) => `${net}: ${amps} A`).join(", ")}</p>
                <details><summary class="cursor-pointer">Finite-copper coil-field limits</summary><p>Direct exterior integration of the exact audited finite-copper current basis. {includeMagnets ? "Analytical PM field added in free space." : "No magnet contribution."} No material reaction, independent AC phase drive, wire substitute or newly qualified field-refinement claim. Projected lines follow Bx/Bz on the selected XZ plane; a purely normal field has no in-plane line. Colors use full |B|. Explicit 3D lines follow XYZ. Seed density is not flux density. Heat uses a separate cycle-average phase-current model. Magnet visibility does not change calculated values.</p></details>
              {:else}
                <details><summary class="cursor-pointer">PM-only model limits</summary><p>Analytical permanent magnets only. No winding or nonlinear material response. Projected lines follow Bx/Bz on the selected XZ plane; a purely normal field has no in-plane line. Colors use full |B|. Explicit 3D lines follow XYZ. Lines stop at magnets or the sampled boundary. Seed density is not flux density. Interpolation is a display approximation, not added physical resolution.</p></details>
              {/if}
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
    <div class="layer-depths pointer-events-none absolute right-12 top-2 text-right font-mono text-[10px] text-slate-400" class:simulation-depths={simulation !== null}>
      {#each geometry?.layer_z_mm ?? [] as z, idx (idx)}
        {#if view.isLayerVisible(idx)}<div>L{idx + 1} · {z.toFixed(2)} mm</div>{/if}
      {/each}
    </div>
    {/if}
  {:else}
    <div class="flex h-full items-center justify-center p-4 text-sm text-slate-500" role="status">{placement.error || "Awaiting coil generation…"}</div>
  {/if}
</div>

<style>
  .coil-3d { container-type: size; }
  .axis-indicator { top: var(--coil-axis-top, .5rem); }
  .overlay-legends { bottom: calc(2rem + var(--coil-overlay-inset, 0px)); max-height: 40cqh; right: auto; max-width: min(26rem, calc(100% - 4.75rem)); }
  .z-height { top: var(--coil-preset-inset, 3rem); bottom: calc(2rem + var(--coil-overlay-inset, 0px)); }
  .simulation-controls { right: 6.25rem; width: 22rem; max-width: calc(100% - 4.5rem); }
  .layer-depths { right: 6.25rem; }
  .inspector-toggle { display: flex; justify-content: space-between; align-items: center; width: 100%; min-height: 2rem; text-align: left; padding: 0.5rem 0.75rem; }
  .inspector-toggle:hover { background: rgb(var(--slate-800)); }
  .overlay-control-fields { display: grid; gap: 0.625rem; padding: 0.625rem; max-height: calc(100cqh - 5rem - var(--coil-overlay-inset, 0px)); overflow-y: auto; border-top: 1px solid rgb(var(--slate-700)); }
  .overlay-control-fields[hidden] { display: none; }
  .control-row { display: grid; grid-template-columns: 5.75rem minmax(0, 1fr); align-items: center; gap: 0.5rem; }
  .control-row select { width: 100%; min-width: 0; min-height: 2rem; }
  .check-row { display: flex; align-items: start; gap: 0.5rem; line-height: 1.4; }
  .check-row input { margin-top: 0.125rem; accent-color: #10b981; }
  .control-section { display: grid; min-width: 0; gap: 0.5rem; border-top: 1px solid rgb(var(--slate-700)); }
  .control-section legend { padding-right: 0.5rem; margin-bottom: 0.5rem; font-weight: 600; color: rgb(var(--slate-200)); }
  .control-hint { color: rgb(var(--slate-400)); font-size: 0.6875rem; line-height: 1.5; }
  .range-control { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 0.25rem 0.5rem; }
  .range-control input { grid-column: 1 / -1; width: 100%; min-width: 0; height: 1.25rem; }
  .range-control output { font-variant-numeric: tabular-nums; color: rgb(var(--slate-200)); }
  .section-button { min-height: 2rem; }
  .section-button[aria-pressed="true"] { border-color: #10b981; color: #10b981; }
  .simulation-depths { display: none; }
  .compact-overlay-toggle { display: none; line-height: 1.4; }
  .compact-overlay-toggle button { padding: .25rem; font-size: inherit; line-height: 1.2; }
  @container (max-width: 760px) {
    .simulation-controls { right: .5rem; top: max(calc(var(--coil-axis-top, .5rem) + 5.5rem), var(--coil-preset-inset, 0px)); }
    .overlay-control-fields { max-height: min(calc(65cqh - 4rem), calc(100cqh - var(--coil-axis-top, .5rem) - 8rem - var(--coil-overlay-inset, 0px))); }
  }
  @container (max-width: 520px) {
    .overlay-legends { bottom: calc(.5rem + var(--coil-overlay-inset, 0px)); }
    .compact-overlay-toggle { display: block; }
    .overlay-legends-body { display: none; }
    .coil-3d[data-legends-open="true"] .overlay-legends-body { display: flex; }
    .layer-depths { display: none; }
    .overlay-control-fields { padding: 0.5rem; }
    .control-row { grid-template-columns: 4.75rem minmax(0, 1fr); }
  }
  @container (max-height: 180px) {
    .z-height { top: var(--coil-preset-inset, 2.75rem); bottom: calc(.25rem + var(--coil-overlay-inset, 0px)); padding: 0.25rem; gap: 0.25rem; }
    .z-label { display: none; }
  }
  button { padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.75rem; }
  button:focus-visible { outline: 2px solid #10b981; }
</style>
