<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import { OrbitControls } from "@threlte/extras";
  import { untrack, tick } from "svelte";
  import { Box3, Vector3, MOUSE, TOUCH, type Group, type OrthographicCamera } from "three";
  import type { OrbitControls as OrbitController } from "three/examples/jsm/controls/OrbitControls.js";
  import { fitCoilCamera, fitCoilWindow, coilWindowFocus, stopCoilCameraMotion, alignTopCamera, type TopCameraTransform } from "../../fitCoilCamera";
  import type { CoilScene, CopperPath } from "../../coilScene";
  import { PHASE_COLORS } from "./coilPreviewCanvas";
  import CoilCopperBatch from "./CoilCopperBatch.svelte";
  import SimulationFieldGlyphs from "./SimulationFieldGlyphs.svelte";
  import SimulationMagnets from "./SimulationMagnets.svelte";
  import type { FieldPreview } from "../../types/simulationVisualization";
  import { HEAT_PALETTE, heatColor } from "../../visualizationGeometry";
  import type { FieldStyle } from "../../simulationFieldGeometry";
  import type { pcbBody } from "../../pcbBody";
  import SpatialMeasureScene from "./SpatialMeasureScene.svelte";
  import type { SpatialMeasure } from "../../spatialMeasure.svelte";
  import ViaPadsBatch from "./ViaPadsBatch.svelte";
  import CoilTerminalMarkers from "./CoilTerminalMarkers.svelte";
  import type { CopperPad } from "../../viaCopperMesh";

  let { scene, paths, vias, pads = [], viaSize = {diameter:.04,drill:.02}, terminals, traceMode, reset, fit = 0, command, windowCommand = {id:0,a:[0,0],b:[1,1]}, zScale, onCamera, viewMode = "iso", topCamera = null, board = null, showPcb = false, measure = null, field = null, heat = null, opacity = .8, fieldStyle = "lines-slice", sliceFraction = .5, sectionView = false, magnets = [] }: {
    scene: CoilScene;
    paths: CopperPath[];
    vias: CoilScene["vias"];
    pads?:CopperPad[];
    viaSize?:{diameter:number;drill:number;plating?:number};
    terminals: CoilScene["terminals"];
    traceMode: "traces" | "centerlines";
    reset: number;
    fit?: number;
    command: { id: number; zoom: number };
    windowCommand?: { id: number; a: [number, number]; b: [number, number] };
    onCamera?: (snapshot: { position: number[]; target: number[]; up: number[]; zoom: number; fitZoom: number }) => void;
    viewMode?: "top" | "front" | "left" | "iso";
    topCamera?: TopCameraTransform | null;
    zScale: number;
    board?: ReturnType<typeof pcbBody> | null;
    showPcb?: boolean;
    measure?: SpatialMeasure | null;
    field?: FieldPreview | null;
    heat?: Map<string, number> | null;
    opacity?: number;
    fieldStyle?: FieldStyle;
    sliceFraction?: number;
    sectionView?: boolean;
    magnets?: FieldPreview["magnets"];
  } = $props();
  const { size, invalidate, dom } = useThrelte();
  let camera = $state.raw<OrthographicCamera>();
  let zoom = $derived(Math.max(1, Math.min($size.width, $size.height) / 14));
  const maximumLoss = $derived(heat ? Math.max(0, ...heat.values()) : 0);
  let batches = $derived(scene.thicknessByLayer.flatMap((thickness, layer) => heat
    ? scene.nets.flatMap(net => [...HEAT_PALETTE, "#64748b"].map(color => ({ key: `${layer}:${net}:${color}`, thickness, color, pads:pads.filter(p=>p.layer===layer&&p.net===net), contextPaths: paths.filter(p => p.layer === layer && p.net === net),
      paths: paths.filter(p => p.layer === layer && p.net === net && (heat.has(p.key) ? heatColor(heat.get(p.key)!, maximumLoss) : "#64748b") === color) })))
    : scene.nets.map((net, idx) => ({ key: `${layer}:${net}`, thickness, color: PHASE_COLORS[idx % PHASE_COLORS.length], pads:pads.filter(p=>p.layer===layer&&p.net===net), contextPaths: paths.filter(p => p.layer === layer && p.net === net), paths: paths.filter(p => p.layer === layer && p.net === net) }))));
  const viaBatches = $derived(heat ? [...HEAT_PALETTE, "#64748b"].map(color => ({ color,
    paths: vias.filter(p => (heat.has(p.key) ? heatColor(heat.get(p.key)!, maximumLoss) : "#64748b") === color) }))
    : [{ color: "#fbbf24", paths: vias }]);
  let content = $state.raw<Group>();
  let controls = $state.raw<OrbitController>();
  let fittedView = "";
  let lastMode = "";
  let lastReset = 0;
  let lastFit = 0;
  let fitZoom = 1;
  let lastScene: CoilScene | null = null;
  let lastZScale = 1;
  let lastField: FieldPreview | null = null;
  let lastSectionView = false;
  // Camera snapshots are imperative navigation state, not reactive geometry.
  const cameras = new Map<string,{position:Vector3;up:Vector3;target:Vector3;zoom:number;fitZoom:number}>();
  function reportCamera() {
    if (camera && controls) onCamera?.({position:camera.position.toArray(),target:controls.target.toArray(),up:camera.up.toArray(),zoom:camera.zoom,fitZoom});
  }
  function rememberPrevious(mode:string) {
    if (camera && controls && lastMode && lastMode !== mode && lastMode !== "top")
      cameras.set(lastMode,{position:camera.position.clone(),up:camera.up.clone(),target:controls.target.clone(),zoom:camera.zoom,fitZoom});
  }
  $effect(() => {
    if (!controls || !camera) return;
    const current = controls, cam = camera;
    const report = () => onCamera?.({ position: cam.position.toArray(), target: current.target.toArray(), up: cam.up.toArray(), zoom: cam.zoom, fitZoom });
    current.addEventListener("change", report);
    return () => current.removeEventListener("change", report);
  });
  $effect(() => {
    if (viewMode === "top" || !controls || !camera) return;
    const current = controls, cam = camera;
    const panScroll = (event: WheelEvent) => {
      // Trackpad translation is a normal wheel event. Pinch is ctrl+wheel
      // and stays with OrbitControls' cursor-centered zoom handler.
      if (event.ctrlKey || !current.enabled) return;
      event.preventDefault(); event.stopImmediatePropagation();
      stopCoilCameraMotion(cam, current);
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? dom.clientHeight : 1;
      const damping = current.enableDamping;
      // The trackpad already supplies inertia; do not add orbit damping to it.
      current.enableDamping = false;
      current.pan(-event.deltaX * unit, -event.deltaY * unit);
      current.enableDamping = damping;
      reportCamera(); invalidate();
    };
    dom.addEventListener("wheel", panScroll, { capture: true, passive: false });
    return () => dom.removeEventListener("wheel", panScroll, true);
  });
  // One controller owns the camera. A separate Bounds controller retains old
  // angles and can silently restore isometric view after selecting XZ.
  $effect(() => {
    const physicalScene=scene, physicalZScale=zScale, currentField=field, sectional=sectionView, currentReset=reset, currentFit=fit;
    const mode = viewMode;
    if (mode === "top" && topCamera) return;
    const viewKey = `${currentReset}:${mode}:${sectional}`;
    // Track resize notifications, but measure after Svelte applies the view's
    // insets. ResizeObserver can still contain the previous view's dimensions.
    void $size.width; void $size.height;
    if (!camera || !controls || !content) return;
    let cancelled = false;
    void tick().then(() => {
      if (cancelled || !camera || !controls || !content) return;
      const width = dom.clientWidth, height = dom.clientHeight;
      stopCoilCameraMotion(camera, controls);
      const physicalChanged=lastScene!==physicalScene || lastZScale!==physicalZScale || lastReset!==currentReset;
      if (physicalChanged) cameras.clear(); else rememberPrevious(mode);
      const modeChanged=lastMode!==mode;
      const needsFit=!lastMode || physicalChanged || lastFit!==currentFit
        || lastSectionView!==sectional || (!modeChanged && lastField!==currentField);
      // A toolbar or dock resize changes the frustum, not the user's pan/zoom.
      // Threlte's automatic camera updates are off so nothing else overwrites it.
      const saved = needsFit ? undefined : modeChanged ? cameras.get(mode) : {
        position:camera.position.clone(),up:camera.up.clone(),target:controls.target.clone(),zoom:camera.zoom,fitZoom,
      };
      const direction = fittedView === viewKey ? camera.position.clone().sub(controls.target)
        : mode === "top" ? new Vector3(0,1,0) : mode === "front" || mode === "iso" && sectional ? new Vector3(0,0,1) : mode === "left" ? new Vector3(-1,0,0) : new Vector3(12,10,14);
      camera.up.set(0,mode === "top" ? 0 : 1,mode === "top" ? -1 : 0);
      content.updateWorldMatrix(true, true);
      let center:Vector3 | null;
      if (saved) {
        camera.position.copy(saved.position);camera.up.copy(saved.up);camera.lookAt(saved.target);
        camera.left=-width/2;camera.right=width/2;camera.top=height/2;camera.bottom=-height/2;
        camera.zoom=saved.zoom;fitZoom=saved.fitZoom;camera.updateProjectionMatrix();camera.updateMatrixWorld(true);
        center=saved.target.clone();
      } else {
        // Invisible PCB/hidden solids must not expand the extents.
        const bounds = new Box3();
        content.traverseVisible(object => {
          if (object.type === "Mesh" || object.type === "LineSegments") bounds.union(new Box3().setFromObject(object, true));
        });
        center = fitCoilCamera(camera, bounds, width, height, direction);
        if (center) fitZoom=camera.zoom;
      }
      if (center) {
        controls.target.copy(center); controls.update(); fittedView = viewKey; invalidate();
        reportCamera();
      }
      lastMode=mode;lastReset=currentReset;lastFit=currentFit;lastScene=physicalScene;lastZScale=physicalZScale;lastField=currentField;lastSectionView=sectional;
    });
    return () => { cancelled = true; };
  });
  $effect(() => {
    const top=topCamera, physicalScene=scene, physicalZScale=zScale, width=$size.width,height=$size.height, currentReset=reset;
    if (viewMode !== "top" || !top || !camera || !controls) return;
    let cancelled=false;
    // OrbitControls updates once when damping is disabled. Apply the exact
    // top projection after those prop updates, then leave its frame task off.
    void tick().then(()=>{
      if(cancelled||!camera||!controls)return;
      if (lastScene!==physicalScene || lastZScale!==physicalZScale || lastReset!==currentReset) cameras.clear();
      else rememberPrevious("top");
      const target=alignTopCamera(camera,physicalScene,top,width,height);
      if (!target) return;
      controls.target.copy(target);
      reportCamera();
      lastMode="top";lastReset=currentReset;lastScene=physicalScene;lastZScale=physicalZScale;invalidate();
    });
    return()=>{cancelled=true;};
  });

  // Button zoom is relative to the current camera, including wheel/pinch changes.
  $effect(() => {
    const { id, zoom: factor } = command;
    // Camera replacement/reset and resizing must not replay the last command.
    untrack(() => {
      if (!id || !camera || viewMode === "top") return;
      if (controls) stopCoilCameraMotion(camera, controls);
      camera.zoom = Math.max(zoom / 20, camera.zoom * factor);
      camera.updateProjectionMatrix();
      reportCamera();
      invalidate();
    });
  });
  $effect(() => {
    const { id, a, b } = windowCommand;
    untrack(() => {
      if (!id || !camera || !controls || !content || viewMode === "top") return;
      stopCoilCameraMotion(camera, controls);
      const focus = coilWindowFocus(camera, content, a, b) ?? controls.target;
      const center = fitCoilWindow(camera, controls.target, a, b, focus);
      if (center) { controls.target.copy(center); controls.update(); reportCamera(); invalidate(); }
    });
  });
</script>

  <T.OrthographicCamera bind:ref={camera} makeDefault manual position={[12, 10, 14]} zoom={1} near={0.01} far={1000}>
    <OrbitControls bind:ref={controls} enabled={viewMode !== "top"} enableRotate={viewMode === "iso"} enableDamping={viewMode === "iso"} zoomToCursor minZoom={zoom / 20} maxZoom={Infinity}
      mouseButtons={{LEFT:viewMode === "iso" ? MOUSE.ROTATE : MOUSE.PAN,MIDDLE:MOUSE.DOLLY,RIGHT:MOUSE.PAN}}
      touches={{ONE:viewMode === "iso" ? TOUCH.ROTATE : TOUCH.PAN,TWO:TOUCH.DOLLY_PAN}} />
  </T.OrthographicCamera>
<T.AmbientLight intensity={1.5} />
<T.DirectionalLight position={[5, 10, 8]} intensity={2} />

{#key scene}
<T.Group bind:ref={content}>
{#if board}
  <T.Mesh position={board.position} visible={showPcb} userData={{ previewBody: true, measureable: true }}>
    <T.BoxGeometry args={board.size} />
    <T.MeshStandardMaterial color="#166534" transparent opacity={0.35} depthWrite={false} />
  </T.Mesh>
{/if}
{#each batches as batch (batch.key)}
  <CoilCopperBatch paths={batch.paths} contextPaths={batch.contextPaths} pads={batch.pads} padDiameter={viaSize.diameter} width={scene.width} thickness={batch.thickness} color={batch.color} {zScale} centerlines={traceMode === "centerlines"} />
{/each}
{#each viaBatches as batch (batch.color)}
  <CoilCopperBatch paths={batch.paths} width={viaSize.drill} plating={viaSize.plating ?? .025*scene.scale} color={batch.color} {zScale} barrels />
{/each}
<ViaPadsBatch pads={vias.length ? pads : []} diameter={viaSize.diameter} drill={viaSize.drill} {zScale}/>
{#if field}<SimulationFieldGlyphs {field} {scene} {zScale} {opacity} style={fieldStyle} {sliceFraction} />{/if}
<SimulationMagnets {magnets} {scene} {zScale} />
</T.Group>
{/key}
<!-- Annotation sizes never participate in the physical camera-fit bounds. -->
<CoilTerminalMarkers {terminals} {scene} {zScale}/>
{#if measure}<SpatialMeasureScene {scene} {measure} {zScale} />{/if}
