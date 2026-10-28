<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { RoutingDimensionsDto } from "../../types";
  import {
    phaseBandPitchMm as phaseBandPitchMmFor,
    restOffsetMm as restOffsetMmFor,
  } from "../../geometry";
  import {
    formatMarginMm,
    formatMetresMm,
    isValidMetres,
  } from "../../previewGeometry";
  import HelpTag from "../ui/HelpTag.svelte";
  import Formula from "../ui/Formula.svelte";
  import windingBandSvg from "../../assets/winding-band.svg";

  let {
    config,
    measuredTraceLengthMm = null,
    routingDimensions = null,
  }: {
    config: ConfigStore;
    /** Trace X-span MEASURED from the returned coil payload (mm); falls back
     *  to the configured routing domain until a payload arrives. */
    measuredTraceLengthMm?: number | null;
    /** `routing_dimensions` sidecar of the last coil payload (metres at the
     *  IPC boundary). Null until a payload arrives; the per-slot metrics
     *  inside are additionally pattern-dependent and stay null when the
     *  pattern declares no leg grid. */
    routingDimensions?: RoutingDimensionsDto | null;
  } = $props();

  // Vernier phase-band pitch / rest-offset formulas live in lib/geometry.
  let phaseBandPitchMm = $derived(
    phaseBandPitchMmFor(config.pole_pitch_mm, config.phases, config.spacing_ratio),
  );
  let restOffsetMm = $derived(
    restOffsetMmFor(config.pole_pitch_mm, config.phases, config.spacing_ratio),
  );

  // --- Routing-payload metrics (metres at the IPC boundary) ---------------
  // Per-slot metrics are pattern-declared: an em-dash means the pattern
  // declares no leg grid (or no payload has arrived yet).

  /** Pass-through for finite positive metre quantities; everything else is null. */
  function validMetres(v: number | null | undefined): number | null {
    return isValidMetres(v) ? v : null;
  }

  let slotCount = $derived(
    typeof routingDimensions?.slot_count === "number" && routingDimensions.slot_count > 0
      ? routingDimensions.slot_count
      : null,
  );
  let slotPitchM = $derived(validMetres(routingDimensions?.slot_pitch_m));
  let interleaveStepM = $derived(validMetres(routingDimensions?.interleave_step_m));

  /**
   * Summarise one metric across all `phase_band_widths` records: a single
   * value when every band agrees (the common case), otherwise the
   * `[min, max]` span. Null when no band reports a finite value.
   */
  function bandValueSpan(values: (number | null | undefined)[]): [number, number] | null {
    let min = Infinity;
    let max = -Infinity;
    for (const v of values) {
      if (typeof v !== "number" || !Number.isFinite(v)) continue;
      min = Math.min(min, v);
      max = Math.max(max, v);
    }
    if (!Number.isFinite(min)) return null;
    return max - min <= 1e-12 ? [min, min] : [min, max];
  }

  let slotWidthM = $derived(
    bandValueSpan((routingDimensions?.phase_band_widths ?? []).map((b) => b.slot_width_m)),
  );
  let bandWidthM = $derived(
    bandValueSpan((routingDimensions?.phase_band_widths ?? []).map((b) => b.band_width_m)),
  );
  let bandMarginM = $derived(
    bandValueSpan((routingDimensions?.phase_band_widths ?? []).map((b) => b.margin_m)),
  );

  /** Single value → one length; a genuine span → "min – max". */
  function formatSpanMm(span: [number, number] | null): string {
    if (!span) return "—";
    return span[0] === span[1]
      ? formatMetresMm(span[0])
      : `${formatMetresMm(span[0])} – ${formatMetresMm(span[1])}`;
  }

  /** Signed margins keep their sign on both ends of a span. */
  function formatMarginSpanMm(span: [number, number] | null): string {
    if (!span) return "—";
    return span[0] === span[1]
      ? formatMarginMm(span[0])
      : `${formatMarginMm(span[0])} – ${formatMarginMm(span[1])}`;
  }

  let slotGroupCaption = $derived(
    routingDimensions === null
      ? "Waiting for geometry"
      : slotCount === null
        ? "No leg grid"
        : "",
  );
</script>

<div class="mt-3 border-t border-slate-700/60 pt-3" aria-label="Derived constraint dimensions">

  <dl class="readout-grid grid grid-cols-2 gap-x-3 gap-y-2">
    <div class="min-w-0">
      <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
        <span class="truncate">PCB trace total (X)</span>
        <HelpTag label="About trace extent" tip="First-to-last trace span. Whole routing periods can make it shorter than the active region." />
      </dt>
      <dd class="font-mono text-xs text-emerald-300">
        {(measuredTraceLengthMm ?? config.trace_total_length_mm).toFixed(1)} mm
        {#if measuredTraceLengthMm !== null}
          <span class="text-[9px] text-slate-500">meas.</span>
        {/if}
      </dd>
    </div>
    <div class="min-w-0">
      <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
        <span class="truncate">Active copper region</span>
        <HelpTag label="About active copper length" tip="Copper length needed to cover the mover throughout its travel." equation={String.raw`L_{\mathrm{active}} = L_{\mathrm{mover}} + d`} />
      </dt>
      <dd class="font-mono text-xs text-emerald-300">{config.active_area_length_mm.toFixed(1)} mm</dd>
    </div>
    <div class="min-w-0">
      <dt class="truncate text-[10px] text-slate-500">Mover span</dt>
      <dd class="font-mono text-xs text-emerald-300">{config.mover_span_mm.toFixed(1)} mm</dd>
    </div>
    <div class="min-w-0">
      <dt class="truncate text-[10px] text-slate-500">Pole pitch</dt>
      <dd class="font-mono text-xs text-emerald-300">{config.pole_pitch_mm.toFixed(2)} mm</dd>
    </div>
    <div class="min-w-0">
      <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
        <span class="truncate">Magnet gap (auto)</span>
        <HelpTag label="About magnet gap" tip="Space between adjacent magnets, set by pole pitch and magnet length." equation={String.raw`g_m = \tau_p - W_m`} />
      </dt>
      <dd class="font-mono text-xs text-emerald-300">{config.magnet_gap_mm.toFixed(1)} mm</dd>
    </div>
    <div class="min-w-0">
      <dt class="flex items-center text-[10px] text-slate-500">Band margin<HelpTag label="About band margin" tip="Available width minus bundle width. A negative value means the bundle does not fit." equation={String.raw`M = W_{\mathrm{available}} - W_{\mathrm{bundle}}`} image={windingBandSvg} imageAlt="Conductor bundle width and the remaining band margin." /></dt>
      <dd class="font-mono text-xs {bandMarginM && bandMarginM[0] < 0 ? 'text-rose-300' : 'text-emerald-300'}">{formatMarginSpanMm(bandMarginM)}</dd>
    </div>
  </dl>

  <!-- All normal dimensions use the same value color; warnings retain their tone. -->
  <details class="mt-3 border-t border-slate-700/60 pt-2">
    <summary class="cursor-pointer text-xs text-slate-400 hover:text-slate-200">Winding dimensions</summary>
    <dl class="readout-grid mt-2 grid grid-cols-2 gap-3">
      <div>
        <dt class="flex items-center text-[10px] text-slate-400">Phase-band pitch<HelpTag label="About phase-band pitch" tip="Band spacing for the Vernier winding. Not the physical slot pitch. Here m is phase count and r is spacing ratio." equation={String.raw`\tau_b = \frac{\tau_p}{m}\,r`} /></dt>
        <dd class="font-mono text-xs text-emerald-300">{phaseBandPitchMm.toFixed(2)} mm</dd>
      </div>
      <div><dt class="text-[10px] text-slate-400">Rest offset</dt><dd class="font-mono text-xs text-emerald-300">{restOffsetMm.toFixed(2)} mm</dd></div>
    </dl>
    <div class="mt-3 space-y-3">
    <div>
      <div class="mb-1 flex items-baseline justify-between gap-2">
        <h3 class="text-xs font-medium text-slate-300">Leg grid</h3>
        {#if slotGroupCaption}
          <span class="text-[9px] text-slate-500">{slotGroupCaption}</span>
        {/if}
      </div>
      <dl class="readout-grid grid grid-cols-2 gap-x-3 gap-y-1.5">
        <div class="min-w-0">
          <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
            <span class="truncate">Slot count</span>
            <HelpTag label="About slot count" tip="Active conductor positions in this pattern. Blank if the pattern has no leg grid." />
          </dt>
          <dd class="font-mono text-xs text-emerald-300">{slotCount ?? "—"}</dd>
        </div>
        <div class="min-w-0">
          <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
            <span class="truncate">Slot pitch <Formula tex={String.raw`\tau_s`} /></span>
            <HelpTag label="About slot pitch" tip="Distance between conductor positions along the stator, not the Vernier band spacing." equation={String.raw`\tau_s = \frac{L_{\mathrm{stator}}}{N_{\mathrm{slots}}}`} />
          </dt>
          <dd class="font-mono text-xs text-emerald-300">{slotPitchM === null ? "—" : formatMetresMm(slotPitchM)}</dd>
        </div>
        <div class="min-w-0">
          <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
            <span class="truncate">Interleave step</span>
            <HelpTag label="About interleave step" tip="Conductor spacing in a braided winding. Here m is phase count and n is strands per period." equation={String.raw`\delta = \frac{\tau_p}{m\,n}`} />
          </dt>
          <dd class="font-mono text-xs text-emerald-300">{interleaveStepM === null ? "—" : formatMetresMm(interleaveStepM)}</dd>
        </div>
        <div class="min-w-0">
          <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
            <span class="truncate">Slot width (one leg)</span>
            <HelpTag label="About slot width" tip="Width of one conductor leg along travel. A range means the bands differ." />
          </dt>
          <dd class="font-mono text-xs text-emerald-300">{formatSpanMm(slotWidthM)}</dd>
        </div>
      </dl>
    </div>
    <div>
      <div class="mb-1 flex items-baseline justify-between gap-2">
        <h3 class="text-xs font-medium text-slate-300">Conductor bundle</h3>
      </div>
      <dl class="readout-grid grid grid-cols-2 gap-x-3 gap-y-1.5">
        <div class="min-w-0">
          <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
            <span class="truncate">Band width (bundle)</span>
            <HelpTag label="About band width" tip="Width of the full conductor bundle along travel. A range means the bands differ." />
          </dt>
          <dd class="font-mono text-xs text-emerald-300">{formatSpanMm(bandWidthM)}</dd>
        </div>
      </dl>
    </div>
    </div>
  </details>
</div>

<style>
  @container (min-width: 560px) {
    .readout-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  }
</style>
