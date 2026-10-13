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
  /** Copper uses physical widths; centerlines use a thin screen-width stroke. */
  traceMode = $state<"traces" | "centerlines">("traces");
  // --- schematic presentation toggles (lightbox controls only) -------------
  /** Show only one repeating electrical period of the winding. Start OFF so
   *  the full winding is visible. */
  oneSection = $state(false);
  /** Pole-pitch ruler toggle. Kept even when no sidecar data exists (the
   *  toggle row simply is not rendered then). */
  showPolePitch = $state(true);
  /** Band-width diagnostics toggle. */
  showBandWidths = $state(true);
  /** Pole-region zone toggle. Default on, like the other overlays. */
  showPoleRegions = $state(true);
  /** Pole-region phase-picker selection; "" = "All phases". Independent of
   *  the per-phase trace visibility toggles. */
  poleRegionPhase = $state("");
  /** Inter-layer via markers. Toggle lives in the expanded lightbox only. */
  showVias = $state(true);

  // --- per-phase + per-layer trace visibility -------------------------------
  // `coils.phases` is one entry per (phase, layer) pair, so phase toggles
  // index against `phase_idx`. Out-of-bounds indices default to visible.
  phaseVisibility = $state<boolean[]>([true, true, true, true, true, true]);

  // Layers are overlaid at their true coordinates, so toggling them is the
  // only way to inspect a single copper layer in isolation. Default: all
  // layers visible (empty record → everything on).
  layerVisibility = $state<Record<number, boolean>>({});

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
