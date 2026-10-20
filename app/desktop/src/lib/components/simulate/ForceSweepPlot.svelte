<script lang="ts">
  import type { CommutationMode, ForceSweepResult } from "../../types";
  import { createLinearScale, paddedRange, ticks, polyline } from "../../chart";

  // Human-readable labels for the raw `CommutationMode` wire values — the UI
  // must not echo snake_case wire values back to the user.
  const COMMUTATION_LABELS: Record<CommutationMode, string> = {
    max_thrust: "Max thrust (FOC)",
    phase_a_only: "Phase A only",
  };

  const commutationLabel = (mode: CommutationMode): string => COMMUTATION_LABELS[mode];

  let { result, embedded = false }: { result: ForceSweepResult | null; embedded?: boolean } = $props();

  let chartWidth = $state(760);
  let chartHeight = $state(240);
  const W = $derived(embedded ? Math.max(320, chartWidth) : 760);
  const H = $derived(embedded ? Math.max(160, chartHeight) : 240);
  const PAD_L = 50;
  const PAD_R = 20;
  const PAD_T = 16;
  const PAD_B = 36;

  let plot = $derived.by(() => {
    if (!result || result.positions_m.length < 2) {
      return null;
    }
    const xs = result.positions_m.map((m) => m * 1000); // → mm
    const ys = result.force_x_n;
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    // pad y range a little (flat data falls back to ±0.001 in chart)
    const [minY, maxY] = paddedRange(ys, 0.08);
    const sx = createLinearScale(minX, maxX, PAD_L, W - PAD_L - PAD_R);
    const sy = createLinearScale(minY, maxY, H - PAD_B, -(H - PAD_T - PAD_B));
    const linePts = polyline(sx, sy, xs, ys);
    // mean line (single straight segment — not an `sx/sy` polyline)
    const meanY = result.mean_thrust_n;
    const meanLine = `${sx(minX).toFixed(1)},${sy(meanY).toFixed(1)} ${sx(maxX).toFixed(1)},${sy(meanY).toFixed(1)}`;
    // y-axis ticks (5)
    const yTicks = ticks(minY, maxY, 5, sy).map((t) => ({ v: t.v, y: t.pos }));
    // x-axis ticks (5)
    const xTicks = ticks(minX, maxX, 5, sx).map((t) => ({ v: t.v, x: t.pos }));
    return { xs, ys, sx, sy, linePts, meanLine, yTicks, xTicks, minY, maxY, minX, maxX, meanY };
  });
</script>

<div class="thrust-panel {embedded ? 'embedded flex h-full min-h-0 flex-col' : 'rounded-lg bg-slate-800/40 border border-slate-700 p-4'}">
  <div class="mb-2 flex shrink-0 flex-wrap items-center justify-between gap-2">
    <h3 class="text-sm font-semibold text-slate-200">Thrust vs. position</h3>
    {#if result}
      <span class="text-xs text-slate-400">
        {commutationLabel(result.commutation)} · I={result.current_a.toFixed(2)} A · n={result.n_positions}
      </span>
    {/if}
  </div>

  <div class="thrust-layout">
  <div class="plot-slot" bind:clientWidth={chartWidth} bind:clientHeight={chartHeight}>
  <svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMinYMin meet" class={embedded ? "block h-full min-h-0 w-full" : "block h-auto w-full"} role="img" aria-label="Thrust sweep plot">
    {#if plot}
      <!-- grid -->
      {#each plot.yTicks as t (t.v)}
        <line x1={PAD_L} y1={t.y} x2={W - PAD_R} y2={t.y} stroke="#334155" stroke-width="0.5" />
        <text x={PAD_L - 6} y={t.y + 3} text-anchor="end" class="fill-slate-500" style="font-size:9px">{t.v.toFixed(3)}</text>
      {/each}
      {#each plot.xTicks as t (t.v)}
        <line x1={t.x} y1={PAD_T} x2={t.x} y2={H - PAD_B} stroke="#1e293b" stroke-width="0.5" />
        <text x={t.x} y={H - PAD_B + 14} text-anchor="middle" class="fill-slate-500" style="font-size:9px">{t.v.toFixed(1)}</text>
      {/each}

      <!-- axes -->
      <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={H - PAD_B} stroke="#475569" stroke-width="1" />
      <line x1={PAD_L} y1={H - PAD_B} x2={W - PAD_R} y2={H - PAD_B} stroke="#475569" stroke-width="1" />
      <text x={W / 2} y={H - 4} text-anchor="middle" class="fill-slate-400" style="font-size:11px">Mover position (mm)</text>
      <text x={14} y={H / 2} text-anchor="middle" transform="rotate(-90 14 {H / 2})" class="fill-slate-400" style="font-size:11px">Thrust (N)</text>

      <!-- thrust polyline -->
      <polyline points={plot.linePts} fill="none" stroke="#10b981" stroke-width="1.6" />

      <!-- mean line -->
      <line x1={plot.sx(plot.minX)} y1={plot.sy(plot.meanY)} x2={plot.sx(plot.maxX)} y2={plot.sy(plot.meanY)}
            stroke="#f59e0b" stroke-width="1" stroke-dasharray="5 3" />
    {:else}
      <text x={W / 2} y={H / 2} text-anchor="middle" class="fill-slate-500" style="font-size:14px">
        Awaiting thrust sweep…
      </text>
    {/if}
  </svg>
  </div>

  {#if plot && result}
    <dl aria-label="Thrust metrics" class="thrust-metrics text-xs">
      <div>
        <dt class="text-slate-400">Mean</dt>
        <dd class="mt-1 font-mono text-base text-emerald-300">{result.mean_thrust_n.toFixed(4)} N</dd>
      </div>
      <div>
        <dt class="text-slate-400">Peak</dt>
        <dd class="mt-1 font-mono text-base text-sky-300">{result.peak_thrust_n.toFixed(4)} N</dd>
      </div>
      <div>
        <dt class="text-slate-400">Min</dt>
        <dd class="mt-1 font-mono text-base text-rose-300">{result.min_thrust_n.toFixed(4)} N</dd>
      </div>
      <div>
        <dt class="text-slate-400">Ripple</dt>
        <dd class="mt-1 font-mono text-base text-amber-300">{result.ripple_pct.toFixed(1)}%</dd>
      </div>
    </dl>
  {/if}
  </div>
</div>

<style>
  .thrust-panel { container-type: inline-size; }
  .thrust-layout { display: grid; min-height: 0; gap: 1rem; }
  .embedded .thrust-layout { flex: 1; grid-template-rows: minmax(160px, 1fr) auto; }
  .plot-slot { min-width: 0; min-height: 0; }
  .thrust-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem 1rem; align-content: start; }
  @container (min-width: 680px) {
    .embedded .thrust-layout { grid-template-columns: minmax(0, 1fr) 12rem; grid-template-rows: minmax(0, 1fr); }
    .embedded .thrust-metrics { grid-template-columns: minmax(0, 1fr); border-left: 1px solid rgb(var(--slate-700)); padding-left: 1rem; }
  }
</style>
