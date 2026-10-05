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
  import Separator from "../ui/Separator.svelte";

  let {
    config,
    measuredTraceLengthMm = null,
    routingDimensions = null,
    cadGeometryActive = false,
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
    /** True when the displayed trace geometry came from a DXF import. */
    cadGeometryActive?: boolean;
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
      ? "waiting for payload"
      : slotCount === null
        ? "no leg grid declared"
        : "",
  );
</script>

<section
  class="rounded-md border border-slate-700 bg-slate-800/40 px-2.5 py-2"
  aria-labelledby="design-dimensions-heading"
>
  <div class="mb-1.5 flex items-center justify-between gap-2">
    <h2 id="design-dimensions-heading" class="text-[11px] font-semibold uppercase tracking-wider text-slate-300">
      Design dimensions
    </h2>
  </div>

  <dl class="grid grid-cols-2 gap-x-3 gap-y-1.5 sm:grid-cols-3">
    <div class="min-w-0">
      <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
        <span class="truncate">PCB trace total (X)</span>
        <HelpTag tip="First-to-last X extent of the routed traces. Whole periods are floored, so it can sit up to one period below the active-area length." />
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
        <HelpTag tip="Mover span + travel." />
      </dt>
      <dd class="font-mono text-xs text-sky-200">{config.active_area_length_mm.toFixed(1)} mm</dd>
    </div>
    <div class="min-w-0">
      <dt class="truncate text-[10px] text-slate-500">Active area width</dt>
      <dd class="font-mono text-xs text-sky-200">{config.active_area_width_mm.toFixed(1)} mm</dd>
    </div>
    <div class="min-w-0">
      <dt class="truncate text-[10px] text-slate-500">Mover span</dt>
      <dd class="font-mono text-xs text-sky-200">{config.mover_span_mm.toFixed(1)} mm</dd>
    </div>
    <div class="min-w-0">
      <dt class="truncate text-[10px] text-slate-500">Pole pitch</dt>
      <dd class="font-mono text-xs text-sky-200">{config.pole_pitch_mm.toFixed(2)} mm</dd>
    </div>
    <div class="min-w-0">
      <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
        <span class="truncate">Phase-band pitch (Vernier)</span>
        <HelpTag label="About phase-band pitch">
          Pole pitch / phases × spacing ratio. Coincides with slot pitch
          <span class="italic">τ<sub>s</sub></span> only for uniform
          1-slot-per-pole-per-phase windings.
        </HelpTag>
      </dt>
      <dd class="font-mono text-xs text-sky-200">{phaseBandPitchMm.toFixed(2)} mm</dd>
    </div>
    <div class="min-w-0">
      <dt class="truncate text-[10px] text-slate-500">Rest offset</dt>
      <dd class="font-mono text-xs text-sky-200">{restOffsetMm.toFixed(2)} mm</dd>
    </div>
    <div class="min-w-0">
      <dt class="truncate text-[10px] text-slate-500">Magnet count</dt>
      <dd class="font-mono text-xs text-sky-200">{config.magnet_count}</dd>
    </div>
    <div class="min-w-0">
      <dt class="truncate text-[10px] text-slate-500">Magnet size</dt>
      <dd class="font-mono text-xs text-sky-200">{config.magnet_width_mm.toFixed(1)} &times; {config.magnet_cross_width_mm.toFixed(1)} mm</dd>
    </div>
    <div class="min-w-0">
      <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
        <span class="truncate">Magnet gap (auto)</span>
        <HelpTag tip="Derived: pole pitch − X Length." />
      </dt>
      <dd class="font-mono text-xs text-sky-200">{config.magnet_gap_mm.toFixed(1)} mm</dd>
    </div>
    <div class="min-w-0">
      <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
        <span class="truncate">{cadGeometryActive ? "Routing pattern" : "Routing"}</span>
        <HelpTag
          tip={cadGeometryActive
            ? "Active trace geometry was imported from a DXF; no generated routing pattern is active."
            : "Active routing pattern id. Switch or add generators in the Design tab's routing-pattern selector."}
        />
      </dt>
      <dd class="truncate font-mono text-xs text-sky-200">
        {cadGeometryActive ? "Imported CAD pattern" : config.routing_pattern}
      </dd>
    </div>
    <div class="min-w-0">
      <dt class="truncate text-[10px] text-slate-500">Layers</dt>
      <dd class="font-mono text-xs text-sky-200">{config.num_layers}</dd>
    </div>
    <div class="min-w-0">
      <dt class="truncate text-[10px] text-slate-500">Phases</dt>
      <dd class="font-mono text-xs text-sky-200">{config.phases}</dd>
    </div>
  </dl>

  <!-- Routing-payload metrics. Payload-derived values are shown like the
       measured trace (emerald); an em-dash means the metric is unavailable. -->
  <div class="mt-2 space-y-2">
    <Separator class="mb-2 bg-slate-700/60" />
    <div>
      <div class="mb-1 flex items-baseline justify-between gap-2">
        <h3 class="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Slot (per-leg)</h3>
        {#if slotGroupCaption}
          <span class="text-[9px] text-slate-500">{slotGroupCaption}</span>
        {/if}
      </div>
      <dl class="grid grid-cols-2 gap-x-3 gap-y-1.5 sm:grid-cols-3">
        <div class="min-w-0">
          <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
            <span class="truncate">Slot count</span>
            <HelpTag tip="Active leg slots declared by the pattern's leg grid; an em-dash when none is declared." />
          </dt>
          <dd class="font-mono text-xs text-emerald-300">{slotCount ?? "—"}</dd>
        </div>
        <div class="min-w-0">
          <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
            <span class="truncate">Slot pitch <span class="italic">τ<sub>s</sub></span></span>
            <HelpTag label="About slot pitch">
              <span class="italic">L<sub>stator</sub></span>/<span class="italic">N<sub>slots</sub></span>
              along the stator track. Not the Vernier phase-band pitch above.
            </HelpTag>
          </dt>
          <dd class="font-mono text-xs text-emerald-300">{slotPitchM === null ? "—" : formatMetresMm(slotPitchM)}</dd>
        </div>
        <div class="min-w-0">
          <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
            <span class="truncate">Interleave step</span>
            <HelpTag tip="Leg pitch of braided/slotless patterns: pole pitch / (phases × strands). No physical slots." />
          </dt>
          <dd class="font-mono text-xs text-emerald-300">{interleaveStepM === null ? "—" : formatMetresMm(interleaveStepM)}</dd>
        </div>
        <div class="min-w-0">
          <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
            <span class="truncate">Slot width (one leg)</span>
            <HelpTag tip="Along-travel width housing one active leg — not the phase-band bundle width below. A range means the bands differ." />
          </dt>
          <dd class="font-mono text-xs text-emerald-300">{formatSpanMm(slotWidthM)}</dd>
        </div>
      </dl>
    </div>
    <div>
      <div class="mb-1 flex items-baseline justify-between gap-2">
        <h3 class="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Phase band (coil bundle)</h3>
      </div>
      <dl class="grid grid-cols-2 gap-x-3 gap-y-1.5 sm:grid-cols-3">
        <div class="min-w-0">
          <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
            <span class="truncate">Band width (bundle)</span>
            <HelpTag tip="Full conductor-bundle width along travel — a band houses the whole coil bundle, a slot one leg. A range means the bands differ." />
          </dt>
          <dd class="font-mono text-xs text-emerald-300">{formatSpanMm(bandWidthM)}</dd>
        </div>
        <div class="min-w-0">
          <dt class="flex min-w-0 items-center gap-0.5 text-[10px] text-slate-500">
            <span class="truncate">Band margin</span>
            <HelpTag tip="Width budget minus band width; negative means over budget." />
          </dt>
          <dd class="font-mono text-xs text-emerald-300">{formatMarginSpanMm(bandMarginM)}</dd>
        </div>
      </dl>
    </div>
  </div>
</section>
