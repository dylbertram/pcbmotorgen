<script lang="ts">
  /**
   * HoldingForceChart.svelte — normalized per-phase holding force versus
   * mover position, tied live to the position slider.
   *
   * One sine wave per phase: F_p(x) = −sin(2π(x − φ − p·P_e/N)/P_e). For a
   * 3-phase motor that is three waves mutually offset by 120° electrical
   * (P_e/3 in space); the phase-A wave's zeros sit on the stable
   * equilibrium rest positions (rest_phase + k·P_e), marked as reference
   * anchors. The slider endpoints are the span-aware flush travel limits
   * (kata 5c7r) and generally do NOT coincide with a zero. Marker dots
   * track the current mover centre on every phase wave.
   */
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { MotionStore } from "../../stores/motion.svelte";
  import { createLinearScale, polyline } from "../../chart";
  import {
    holdingForceAtPhase,
    sampleHoldingForce,
    restPositions,
    phaseStroke,
    phaseFill,
  } from "../../holdingForce";

  let { config, motion, flush = false }: { config: ConfigStore; motion: MotionStore; flush?: boolean } = $props();

  const W = 560;
  const H = 88;
  const PAD_X = 8;
  const PAD_Y = 12;

  let minX = $derived(motion.moverMinMm);
  let maxX = $derived(Math.max(motion.moverMinMm + 1e-6, motion.moverMaxMm));

  let phaseCount = $derived(Math.max(1, Math.floor(config.phases)));

  // Shared sample grid; each phase wave is evaluated on the same xs.
  let samples = $derived.by(() =>
    sampleHoldingForce(minX, maxX, motion.restPhaseMm, motion.electricalPeriodMm, 240),
  );

  /** Per-phase polyline point strings, indexed by phase. */
  let wavePoints = $derived.by(() => {
    const sx = createLinearScale(minX, maxX, PAD_X, W - 2 * PAD_X);
    const sy = createLinearScale(-1.15, 1.15, H - PAD_Y, -(H - 2 * PAD_Y));
    return Array.from({ length: phaseCount }, (_, p) =>
      polyline(
        sx,
        sy,
        samples.xs,
        samples.ys.map((_, i) =>
          holdingForceAtPhase(samples.xs[i], p, phaseCount, motion.restPhaseMm, motion.electricalPeriodMm),
        ),
      ),
    );
  });

  let sx = $derived(createLinearScale(minX, maxX, PAD_X, W - 2 * PAD_X));
  let sy = $derived(createLinearScale(-1.15, 1.15, H - PAD_Y, -(H - 2 * PAD_Y)));
  let zeroY = $derived(sy(0));
  let rests = $derived(restPositions(minX, maxX, motion.restPhaseMm, motion.electricalPeriodMm));

  let markerX = $derived(sx(motion.clampedPositionMm));
  /** Marker dot y per phase at the current position. */
  let markerYs = $derived.by(() =>
    Array.from({ length: phaseCount }, (_, p) =>
      sy(holdingForceAtPhase(motion.clampedPositionMm, p, phaseCount, motion.restPhaseMm, motion.electricalPeriodMm)),
    ),
  );
</script>

<svg
  viewBox="0 0 {W} {H}"
  role="img"
  aria-label="Per-phase holding force versus mover position ({phaseCount} waves offset by {Math.round(360 / phaseCount)} degrees)"
  class="block w-full rounded-md border border-slate-700/80 bg-slate-900/40 {flush ? '' : 'mt-2'}"
>
  <!-- ±1 gridlines -->
  <line x1={PAD_X} x2={W - PAD_X} y1={sy(1)} y2={sy(1)} class="stroke-slate-700/60" stroke-dasharray="3 4" />
  <line x1={PAD_X} x2={W - PAD_X} y1={sy(-1)} y2={sy(-1)} class="stroke-slate-700/60" stroke-dasharray="3 4" />

  <!-- zero-force axis -->
  <line x1={PAD_X} x2={W - PAD_X} y1={zeroY} y2={zeroY} class="stroke-slate-600" />

  <!-- stable rest positions (phase-A force zero-crossings) -->
  {#each rests as r (r)}
    <line
      x1={sx(r)}
      x2={sx(r)}
      y1={zeroY - 4}
      y2={zeroY + 4}
      class="stroke-sky-400/70"
      stroke-width="1.5"
    />
  {/each}

  <!-- one holding-force wave per phase (120° offsets for 3 phases) -->
  {#each wavePoints as points, p (p)}
    <polyline points={points} fill="none" class={phaseStroke(p)} stroke-width="1.5" opacity="0.9">
      <title>Phase {"ABC"[p] ?? p + 1}</title>
    </polyline>
  {/each}

  <!-- current-position marker: one dot per phase -->
  <line x1={markerX} x2={markerX} y1={PAD_Y - 6} y2={H - PAD_Y + 2} class="stroke-emerald-300/40" />
  {#each markerYs as my, p (p)}
    <circle cx={markerX} cy={my} r="2.5" class={phaseFill(p)}>
      <title>{"ABC"[p] ?? p + 1} @ {motion.clampedPositionMm.toFixed(1)} mm</title>
    </circle>
  {/each}

  <!-- labels -->
  <text x={PAD_X + 2} y={sy(1) + 9} class="fill-slate-500 text-[8px]">F (norm.)</text>
  <text x={PAD_X} y={H - 2} class="fill-slate-500 text-[8px]">{minX.toFixed(0)} mm</text>
  <text x={W - PAD_X} y={H - 2} text-anchor="end" class="fill-slate-500 text-[8px]">{maxX.toFixed(0)} mm</text>
</svg>
