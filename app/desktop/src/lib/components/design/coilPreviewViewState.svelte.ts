/**
 * coilPreviewViewState.svelte.ts
 * ============================================================================
 * Shared presentation state for the coil preview's two views (the inline
 * card and the expanded lightbox).
 *
 * CoilPreview instantiates this class ONCE and passes it down, so the
 * renderer's draw effect and the CoilPreviewLightbox toggle row read and
 * write ONE source of truth: a toggle flipped in the lightbox immediately
 * repaints the shared schematic, and the state survives open/close cycles.
 *
 * The class carries NO geometry: what the toggles DO (camera-fit unions,
 * segment filters, zone filtering) is derived in lib/previewGeometry
 * consumers (CoilPreview.svelte) — this is the plain presentation state.
 */

export class CoilPreviewViewState {
  /** Shared copper renderer with orthographic presets and an orbitable 3D view. */
  viewMode = $state<"top" | "front" | "left" | "iso">("top");
  zoomWindow = $state(false);
  /** Shared viewport controls dispatch to the spatial camera when not in Top. */
  cameraCommand = $state({ id: 0, zoom: 1 });
  cameraReset = $state(0);
  cameraFit = $state(0);
  spatialZoom = $state(1);
  /** Copper uses physical widths; centerlines use a thin screen-width stroke. */
  traceMode = $state<"traces" | "centerlines">("traces");
  /** Phase waveform below the mover slider in the expanded preview. */
  showWaveform = $state(true);
  // --- schematic presentation toggles (lightbox controls only) -------------
  /** Show only one repeating electrical period of the winding. Start OFF so
   *  the full winding is visible. */
  oneSection = $state(false);
  /** Pole-pitch ruler toggle. Kept even when no sidecar data exists (the
   *  toggle row simply is not rendered then). */
  showPolePitch = $state(true);
  /** Detailed diagnostics are opt-in so they do not obscure the working drawing. */
  showBandWidths = $state(false);
  showPoleRegions = $state(false);
  /** Pole-region phase-picker selection; "" = "All phases". Independent of
   *  the per-phase trace visibility toggles. */
  poleRegionPhase = $state("");
  /** Inter-layer via markers. Toggle lives in the expanded lightbox only. */
  showVias = $state(true);
  showPcb = $state(false);
  showTerminals = $state(true);
  terminalPanelOpen = $state(false);
  positionBarMode = $state<"position" | "layers">("position");
  /** Measured overlay height, reserved by the endpoint-picking camera fit. */
  positionBarHeight = $state(0);

  setTerminalPanelOpen(open: boolean): void {
    if (open && !this.terminalPanelOpen) this.positionBarMode = "layers";
    if (!open && this.terminalPanelOpen) this.positionBarMode = "position";
    this.terminalPanelOpen = open;
  }

  // --- outside requests -----------------------------------------------------
  /** Incremented by an outside prompt (the Simulation tab's ends alert) to
   *  open the coil-ends panel in the expanded preview. CoilPreview watches
   *  the counter, so repeated requests always fire. */
  terminalRequest = $state(0);
  requestedTerminalCoil = $state<string | undefined>(undefined);

  requestTerminals(coil?: string): void {
    this.requestedTerminalCoil = coil;
    this.setTerminalPanelOpen(true);
    this.terminalRequest += 1;
  }

  // --- per-phase + per-layer trace visibility -------------------------------
  // `coils.phases` is one entry per (phase, layer) pair, so phase toggles
  // index against `phase_idx`. Out-of-bounds indices default to visible.
  phaseVisibility = $state<boolean[]>([true, true, true, true, true, true]);

  // Layers are overlaid at their true coordinates, so toggling them is the
  // only way to inspect a single copper layer in isolation. Default: all
  // layers visible (empty record → everything on).
  layerVisibility = $state<Record<number, boolean>>({});
  coilLayerVisibility = $state<Record<string, boolean>>({});
  /** Changes only the organization of the Layers drawer, never its filters. */
  layerSortMode = $state<"phases" | "layers">("phases");

  isCoilLayerVisible(coil: string, layer: number): boolean {
    return this.coilLayerVisibility[JSON.stringify([coil, layer])] !== false;
  }

  toggleCoilLayer(coil: string, layer: number): void {
    const key = JSON.stringify([coil, layer]);
    this.coilLayerVisibility = { ...this.coilLayerVisibility, [key]: !this.isCoilLayerVisible(coil, layer) };
  }

  showCoilLayer(coil: string, layer: number): void {
    this.coilLayerVisibility = { ...this.coilLayerVisibility, [JSON.stringify([coil, layer])]: true };
  }

  isPhaseVisible(phaseIdx: number): boolean {
    return this.phaseVisibility[phaseIdx] !== false;
  }

  isLayerVisible(layerIdx: number): boolean {
    return this.layerVisibility[layerIdx] !== false;
  }

  toggleLayer(layerIdx: number): void {
    this.layerVisibility = {
      ...this.layerVisibility,
      [layerIdx]: !this.isLayerVisible(layerIdx),
    };
  }
}
