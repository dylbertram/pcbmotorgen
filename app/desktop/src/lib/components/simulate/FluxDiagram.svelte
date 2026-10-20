<!--
  FluxDiagram.svelte — B-field arrow grid for the linear PCB motor.

  Implements ADR-0002 (flux viz via Rust `sample_b_field`) and ADR-0003
  (auto-refresh on dimension change). The grid of vectors
  comes from `sampleBField` in `lib/ipc`; the Rust
  `pcbmotorgen_simulation::physics` adapter is the sole authoritative source
  for the B-field math — `magpylib` is never imported.
-->
<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import { sampleBField, debounce, mm } from "../../ipc";
  import { computeMagnets } from "../../previewGeometry";
  import type { BFieldGridDto } from "../../types";
  import HelpTag from "../ui/HelpTag.svelte";
  import Formula from "../ui/Formula.svelte";

  let { config, active, embedded = false }: { config: ConfigStore; active: boolean; embedded?: boolean } = $props();

  // --- SVG canvas (matches CoilPreview width) -----------------------
  const W = 760;
  const H = 280;
  const PAD_L = 56;
  const PAD_R = 18;
  const PAD_T = 18;
  const PAD_B = 36;

  /**
   * Arrow length factor — metres of arrow per Tesla of B-field magnitude.
   *
   * The X extent (~200 mm) is ~30× the Z extent (~6.5 mm) for a typical
   * PCB linear motor, so a single scalar k stretches the Z components
   * ~10× more than the X components. With k = 0.003 m/T and a 0.5 T
   * field, arrows render as ~5–6 px in X and ~55 px in Z — visible
   * without filling the plot. Tunable if a different geometry is
   * needed; the spec example was 0.005 m/T.
   */
  const K_M_PER_T = 0.003;

  /** Skip arrows whose magnitude is below this fraction of the grid max. */
  const MAG_FRACTION_MIN = 0.05;

  /** Arrowhead size (px). */
  const HEAD_PX = 4;
  const clipId = $props.id();

  /**
   * 5-stop colour-blind-safe sequential palette (per ADR-0002):
   *   0.0–0.2  #1e3a8a  dark blue   (low magnitude)
   *   0.2–0.4  #0891b2  cyan
   *   0.4–0.6  #65a30d  green
   *   0.6–0.8  #ca8a04  amber
   *   0.8–1.0  #dc2626  red         (high magnitude)
   *
   * Justification: the blue→cyan and amber→red boundaries differ in
   * both hue and luminance, so the ramp remains readable for
   * deuteranopes and protanopes (the most common red–green colour
   * vision deficiencies). Picked over Okabe-Ito (which is categorical)
   * because we need a sequential, magnitude-ordered scale.
   */
  const PALETTE = ["#1e3a8a", "#0891b2", "#65a30d", "#ca8a04", "#dc2626"];

  /**
   * Magnet pole fill colors — mirror the TravelDiagram convention
   * (N = orange, S = blue) so the cross-section legend matches the
   * schematic the user already knows.
   */
  const MAGNET_N_COLOR = "#f97316";
  const MAGNET_S_COLOR = "#3b82f6";

  function magnitudeColor(frac: number): string {
    if (!isFinite(frac) || frac < 0) return PALETTE[0];
    if (frac < 0.2) return PALETTE[0];
    if (frac < 0.4) return PALETTE[1];
    if (frac < 0.6) return PALETTE[2];
    if (frac < 0.8) return PALETTE[3];
    return PALETTE[4];
  }

  // --- Reactive state -------------------------------------------------
  let grid = $state<BFieldGridDto | null>(null);
  let sampling = $state(false);
  let loading = $derived(active && sampling);
  let error = $state<string | null>(null);

  // Sequence number to ignore stale responses from earlier samples and to
  // invalidate a request as soon as the tab is hidden.
  let sampleSeq = 0;

  // --- Debounced sampling (150 ms — matches App.svelte throttle) ----
  const sample = debounce(async (seq: number) => {
    if (!active || seq !== sampleSeq) return;
    sampling = true;
    error = null;
    try {
      const result = await sampleBField(config.toIpc());
      if (seq !== sampleSeq) return; // stale — a newer sample is in flight
      grid = result;
    } catch (e) {
      if (seq !== sampleSeq) return;
      error = e instanceof Error ? e.message : String(e);
    } finally {
      if (seq === sampleSeq) sampling = false;
    }
  }, 150);

  // --- Auto-refresh on watched config fields (ADR-0003) --------------
  // Touch every field that affects the B-field sample; the void-array
  // is the Svelte 5 idiom for "read all of these for tracking, then
  // discard". Entering the Simulation tab triggers an initial sample;
  // subsequent field changes re-run sample() after the 150 ms debounce.
  // Leaving the tab cancels pending work and invalidates in-flight results.
  $effect(() => {
    void [
      config.magnet_width_mm,
      config.magnet_cross_width_mm,
      config.magnet_height_mm,
      config.air_gap_mm,
      config.magnet_count,
      config.magnet_gap_mm,
      config.magnet_remanence_t,
      config.magnet_grade,
      config.active_area_length_mm,
    ];
    const seq = ++sampleSeq;
    if (!active) {
      sample.cancel();
      return;
    }
    sample(seq);
  });

  // --- Derived: pixel transform, max magnitude, arrow descriptors ---
  let plot = $derived.by(() => {
    if (!grid || grid.samples.length === 0) return null;
    const [xMin, xMax] = grid.x_extent_m;
    const [zMin, zMax] = grid.z_extent_m;
    const xRange = Math.max(xMax - xMin, 1e-9);
    const zRange = Math.max(zMax - zMin, 1e-9);
    const scaleX = (W - PAD_L - PAD_R) / xRange;
    const scaleZ = (H - PAD_T - PAD_B) / zRange;

    const sx = (x: number) => PAD_L + (x - xMin) * scaleX;
    const sy = (z: number) => H - PAD_B - (z - zMin) * scaleZ;
    const sw = (m: number) => m * scaleX; // pixel width per metre on X
    const sh = (m: number) => m * scaleZ; // pixel height per metre on Z

    let maxMag = 0;
    for (const s of grid.samples) if (s.mag_t > maxMag) maxMag = s.mag_t;
    if (maxMag <= 0) {
      return { sx, sy, sw, sh, arrows: [] as { x1: number; y1: number; x2: number; y2: number; color: string }[], maxMag: 0, xTicks: [] as { v: number; x: number }[], zTicks: [] as { v: number; y: number }[] };
    }

    const threshold = maxMag * MAG_FRACTION_MIN;
    const arrows: { x1: number; y1: number; x2: number; y2: number; color: string }[] = [];
    for (const s of grid.samples) {
      if (s.mag_t < threshold) continue;
      const x1 = sx(s.x_m);
      const y1 = sy(s.z_m);
      const x2 = sx(s.x_m + K_M_PER_T * s.bx_t);
      const y2 = sy(s.z_m + K_M_PER_T * s.bz_t);
      const len = Math.hypot(x2 - x1, y2 - y1);
      // Skip near-degenerate arrows (rounding noise / zero vector).
      if (len < 0.5) continue;
      arrows.push({ x1, y1, x2, y2, color: magnitudeColor(s.mag_t / maxMag) });
    }

    // 5 ticks per axis (min, 1/4, 1/2, 3/4, max).
    const xTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => ({
      v: xMin + f * xRange,
      x: sx(xMin + f * xRange),
    }));
    const zTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => ({
      v: zMin + f * zRange,
      y: sy(zMin + f * zRange),
    }));

    return { sx, sy, sw, sh, arrows, maxMag, xTicks, zTicks };
  });

  // --- Derived: reference geometry (PCB, air gap, magnets) --
  // Reads straight from `config` (mm) and converts to metres with `mm()`.
  // Independent of `plot` so the geometry is responsive the moment a
  // input changes — the arrows catch up 150 ms later after sampling.
  let geom = $derived.by(() => {
    // Read the watched fields explicitly so Svelte 5 tracks every one
    // as a dependency of this derived (the void-discard idiom is the
    // canonical "read but discard" pattern; harmless if a value is also
    // used in the body).
    void config.air_gap_mm;
    void config.magnet_height_mm;
    void config.magnet_width_mm;
    void config.magnet_gap_mm;
    void config.active_area_length_mm;

    const airGapM = mm(config.air_gap_mm);
    const magnetHM = mm(config.magnet_height_mm);
    const magnetWM = mm(config.magnet_width_mm);
    const magnetGM = mm(config.magnet_gap_mm);
    const activeLenM = mm(config.active_area_length_mm);
    return {
      air_gap_top_m: airGapM, // bottom of magnets
      magnet_top_m: airGapM + magnetHM, // top of magnets
      magnet_width_m: magnetWM,
      magnet_pitch_m: magnetWM + magnetGM, // width + gap
      magnet_count: config.magnet_count,
      active_area_length_m: activeLenM,
    };
  });

  /** Magnet bars use the shared centered pitch-cell fallback. */
  let magnetBars = $derived(computeMagnets(config));
</script>

<div class={embedded ? "flex h-full min-h-0 flex-col" : "rounded-lg bg-slate-800/40 border border-slate-700 p-4"}>
  <div class="flex items-center justify-between mb-2 flex-wrap gap-2">
    <h3 class="text-sm font-semibold text-slate-200">
      Magnetic flux density <Formula tex={String.raw`\mathbf{B}`} />
      <HelpTag label="About the magnetic field plot" tip="X–Z section averaged across Y. Arrows show field direction and relative strength. Geometry is not to scale." />
    </h3>
    <span class="text-xs text-slate-400">
      {#if loading}Sampling…{/if}
    </span>
  </div>

  <svg viewBox="0 0 {W} {H}" class={embedded ? "min-h-0 w-full flex-1" : "w-full h-auto"} role="img" aria-label="B-field flux density">
    <defs><clipPath id={clipId}><rect x={PAD_L} y={PAD_T} width={W - PAD_L - PAD_R} height={H - PAD_T - PAD_B} /></clipPath></defs>
    <!-- Plot frame -->
    <rect
      x={PAD_L - 8}
      y={PAD_T - 8}
      width={W - PAD_L - PAD_R + 16}
      height={H - PAD_T - PAD_B + 16}
      fill="rgb(var(--slate-900))"
      stroke="#334155"
      stroke-width="1"
      rx="6"
    />

    {#if error}
      <text
        x={W / 2}
        y={H / 2}
        text-anchor="middle"
        class="fill-rose-300"
        style="font-size:13px"
      >
        B-field sampling error: {error}
      </text>
    {:else if !plot}
      <text
        x={W / 2}
        y={H / 2}
        text-anchor="middle"
        class="fill-slate-500"
        style="font-size:14px"
      >
        Sampling…
      </text>
    {:else}
      <!-- Grid lines -->
      {#each plot.zTicks as t (t.v)}
        <line x1={PAD_L} y1={t.y} x2={W - PAD_R} y2={t.y} stroke="#1e293b" stroke-width="0.5" />
      {/each}
      {#each plot.xTicks as t (t.v)}
        <line x1={t.x} y1={PAD_T} x2={t.x} y2={H - PAD_B} stroke="#1e293b" stroke-width="0.5" />
      {/each}

      <!-- Axes -->
      <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={H - PAD_B} stroke="#475569" stroke-width="1" />
      <line x1={PAD_L} y1={H - PAD_B} x2={W - PAD_R} y2={H - PAD_B} stroke="#475569" stroke-width="1" />
      <text
        x={W / 2}
        y={H - 4}
        text-anchor="middle"
        class="fill-slate-400"
        style="font-size:11px"
      >
        X (m)
      </text>
      <text
        x={14}
        y={H / 2}
        text-anchor="middle"
        transform="rotate(-90 14 {H / 2})"
        class="fill-slate-400"
        style="font-size:11px"
      >
        Z (m)
      </text>

      <!-- X tick labels (metres) -->
      {#each plot.xTicks as t (t.v)}
        <text
          x={t.x}
          y={H - PAD_B + 14}
          text-anchor="middle"
          class="fill-slate-500"
          style="font-size:9px"
        >
          {t.v.toFixed(3)}
        </text>
      {/each}
      <!-- Z tick labels (metres) -->
      {#each plot.zTicks as t (t.v)}
        <text
          x={PAD_L - 6}
          y={t.y + 3}
          text-anchor="end"
          class="fill-slate-500"
          style="font-size:9px"
        >
          {t.v.toFixed(4)}
        </text>
      {/each}

      <!-- ============================================================ -->
      <!-- Reference geometry (drawn BEHIND the arrows).                 -->
      <!-- Static cross-section: PCB surface, air gap, magnet bars, and  -->
      <!-- active-area end-stops. Dimmer than the arrows so the B-field  -->
      <!-- remains the primary visual.                                   -->
      <!-- ============================================================ -->

      <!-- Copper active-area edges (active area start / active area end) = the routing domain bounds -->
      <line
        x1={plot.sx(0)}
        y1={PAD_T}
        x2={plot.sx(0)}
        y2={H - PAD_B}
        stroke="#64748b"
        stroke-width="1"
        stroke-dasharray="3 3"
        stroke-opacity="0.4"
      />
      <line
        x1={plot.sx(geom.active_area_length_m)}
        y1={PAD_T}
        x2={plot.sx(geom.active_area_length_m)}
        y2={H - PAD_B}
        stroke="#64748b"
        stroke-width="1"
        stroke-dasharray="3 3"
        stroke-opacity="0.4"
      />
      <text
        x={plot.sx(0) + 3}
        y={H - PAD_B - 3}
        class="fill-slate-500"
        style="font-size:8px"
      >
        Active area start
      </text>
      <text
        x={plot.sx(geom.active_area_length_m) - 3}
        y={H - PAD_B - 3}
        text-anchor="end"
        class="fill-slate-500"
        style="font-size:8px"
      >
        Active area end
      </text>

      <!-- PCB top surface (Z = 0) -->
      <line
        x1={PAD_L}
        y1={plot.sy(0)}
        x2={W - PAD_R}
        y2={plot.sy(0)}
        stroke="#64748b"
        stroke-width="1.5"
        stroke-opacity="0.6"
      />
      <text
        x={W - PAD_R - 4}
        y={plot.sy(0) - 3}
        text-anchor="end"
        class="fill-slate-400"
        style="font-size:9px"
      >
        PCB (F.Cu)
      </text>

      <!-- Air gap top (Z = air_gap) — dashed line, where the magnets start -->
      <line
        x1={PAD_L}
        y1={plot.sy(geom.air_gap_top_m)}
        x2={W - PAD_R}
        y2={plot.sy(geom.air_gap_top_m)}
        stroke="#64748b"
        stroke-width="1"
        stroke-dasharray="4 3"
        stroke-opacity="0.45"
      />
      <text
        x={PAD_L + 4}
        y={plot.sy(geom.air_gap_top_m) - 2}
        class="fill-slate-400"
        style="font-size:9px"
      >
        Air gap
      </text>

      <!-- Magnet bars — alternating N (orange) / S (blue), fill-opacity 0.35. -->
      {#each magnetBars as m, i (i)}
        <rect
          x={plot.sx(m.x)}
          y={plot.sy(geom.magnet_top_m)}
          width={Math.max(plot.sw(m.w), 0.5)}
          height={Math.max(plot.sh(geom.magnet_top_m - geom.air_gap_top_m), 0.5)}
          fill={m.pole > 0 ? MAGNET_N_COLOR : MAGNET_S_COLOR}
          fill-opacity="0.35"
          stroke={m.pole > 0 ? MAGNET_N_COLOR : MAGNET_S_COLOR}
          stroke-width="0.5"
          stroke-opacity="0.6"
        />
      {/each}

      <!-- Arrows -->
      <g clip-path={`url(#${clipId})`}>
      {#each plot.arrows as a, i (i)}
        {@const dx = a.x2 - a.x1}
        {@const dy = a.y2 - a.y1}
        {@const len = Math.hypot(dx, dy)}
        {@const ux = dx / len}
        {@const uy = dy / len}
        {@const hx1 = a.x2 - ux * HEAD_PX + uy * (HEAD_PX * 0.5)}
        {@const hy1 = a.y2 - uy * HEAD_PX - ux * (HEAD_PX * 0.5)}
        {@const hx2 = a.x2 - ux * HEAD_PX - uy * (HEAD_PX * 0.5)}
        {@const hy2 = a.y2 - uy * HEAD_PX + ux * (HEAD_PX * 0.5)}
        <g>
          <line
            x1={a.x1}
            y1={a.y1}
            x2={a.x2}
            y2={a.y2}
            stroke={a.color}
            stroke-width="1.4"
            stroke-opacity="0.85"
            stroke-linecap="round"
          />
          <polygon
            points="{a.x2},{a.y2} {hx1},{hy1} {hx2},{hy2}"
            fill={a.color}
            fill-opacity="0.9"
          />
        </g>
      {/each}
      </g>
    {/if}
  </svg>

  {#if plot && !error}
    <div class="mt-2 flex items-center justify-between flex-wrap gap-2 text-xs">
      <div class="flex items-center gap-2">
        <span class="text-slate-400"><Formula tex={String.raw`\max |\mathbf{B}|`} /></span>
        <span class="font-mono text-sky-300">{plot.maxMag.toFixed(3)} T</span>
        <span class="text-slate-500">·</span>
        <span class="text-slate-400">{plot.arrows.length} arrows</span>
      </div>
      <div class="flex items-center gap-1.5">
        <span class="text-slate-500">low</span>
        {#each PALETTE as c, i (i)}
          <span
            class="inline-block h-2.5 w-5 rounded-sm border border-slate-700"
            style:background-color={c}
          ></span>
        {/each}
        <span class="text-slate-500">high</span>
      </div>
    </div>
  {/if}
</div>
