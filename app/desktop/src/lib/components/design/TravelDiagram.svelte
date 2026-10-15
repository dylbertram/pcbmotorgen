<script lang="ts">
  /**
   * TravelDiagram.svelte — two views of the stator / mover assembly.
   *
   *   1. 3/4 isometric view (TravelIsoView): axonometric projection of
   *      the assembly (PCB wireframe + magnet wireframe). Z is exaggerated
   *      so the thin stackup is visible. The magnet block sits at the
   *      current mover position along the travel axis.
   *
   *   2. Front-on orthographic view (TravelStackupView): Y–Z
   *      cross-section; each layer is a full-width rectangle. The N·S
   *      pole alternation happens along the TRAVEL direction (X), which
   *      is perpendicular to this view, so the magnet block is uniform
   *      and a "N · S" label makes the alternation axis explicit.
   *
   *   The mover position is shared with the CoilPreview via the MotionStore
   *   owned by App.svelte: the slider / number field below commit into it,
   *   and the CoilPreview magnet strip reflects the same position. The value
   *   is the CENTER of the magnet array in mm, clamped to the movable range
   *   (continuous — a coreless motor has no detent/cogging force; slider endpoints are stable rest positions spaced one electrical period P_e apart).
   */
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { MotionStore } from "../../stores/motion.svelte";
  import { stripBoundsDomainMm, type TraceMeasure } from "../../previewGeometry";
  import MoverPositionControls from "./MoverPositionControls.svelte";
  import TravelIsoView from "./TravelIsoView.svelte";
  import TravelStackupView from "./TravelStackupView.svelte";

  let {
    config,
    motion,
    measuredTrace = null,
  }: {
    config: ConfigStore;
    motion: MotionStore;
    /** Geometry MEASURED from the returned coil payload — the same numbers
     *  the coil canvas draws. Null until the first payload arrives. */
    measuredTrace?: TraceMeasure | null;
  } = $props();

  let invalid = $derived(config.travel_mm <= 0);

  /**
   * Mover strip extent (mm) in the DOMAIN frame — centred on the shared
   * MotionStore position via `stripBoundsDomainMm`, the same anchor used by
   * the canvas overlay and readouts, so every drawn edge and printed number
   * agrees.
   */
  let stripBounds = $derived(stripBoundsDomainMm(config, motion));

  /** Board length shown in the header: MEASURED when available, else configured. */
  let tracesLabelMm = $derived(
    measuredTrace?.traceLengthMm ?? config.trace_total_length_mm,
  );
</script>

<div class="rounded-lg bg-slate-800/40 border border-slate-700 p-4">
  <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
    <div>
      <h2 class="text-sm font-semibold text-slate-200">Design reflection</h2>
      <p class="text-[11px] text-slate-500">Live stackup and travel geometry</p>
    </div>
    <span class="text-xs text-slate-400" role="status" aria-live="polite">
      traces = {tracesLabelMm.toFixed(1)} mm{measuredTrace
        ? " (measured)"
        : ""} · active = {config.active_area_length_mm.toFixed(
        1,
      )} mm · mover_span = {config.mover_span_mm.toFixed(
        1,
      )} mm ·
      <span class={invalid ? "text-rose-400" : "text-sky-300"}
        >L_travel = {config.travel_mm.toFixed(1)} mm</span
      >
    </span>
  </div>

  <div class="grid grid-cols-1 md:grid-cols-[1fr_180px] gap-3 items-start">
    <!-- ===== 1. 3/4 isometric view ===== -->
    <TravelIsoView
      {config}
      {measuredTrace}
      stripStartMm={stripBounds.startMm}
      stripEndMm={stripBounds.endMm}
    />

    <!-- ===== 2. Front-on orthographic stackup (Y–Z) ===== -->
    <TravelStackupView {config} />
  </div>

  <!-- ===== 3. Mover position: shared controls (also shown in the coil
       preview lightbox) ===== -->
  <MoverPositionControls {config} {motion} />

  {#if invalid}
    <p class="mt-3 text-xs text-rose-400">
      Travel is zero or negative — increase Desired Travel (center-to-center) or
      reduce Magnet Count / Width / Gap.
    </p>
  {/if}
</div>
