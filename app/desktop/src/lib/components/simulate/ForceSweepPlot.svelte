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

  let { result }: { result: ForceSweepResult | null } = $props();

  const W = 760;
  const H = 240;
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

<div class="rounded-lg bg-slate-800/40 border border-slate-700 p-4">
  <div class="flex items-center justify-between mb-2">
    <h3 class="text-sm font-semibold text-slate-200">Thrust vs. position</h3>
    {#if result}
      <span class="text-xs text-slate-400">
        {commutationLabel(result.commutation)} · I={result.current_a.toFixed(2)} A · n={result.n_positions}
      </span>
    {/if}
  </div>

  <svg viewBox="0 0 {W} {H}" class="w-full h-auto" role="img" aria-label="Thrust sweep plot">
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

  {#if plot && result}
    <div class="mt-2 grid grid-cols-4 gap-2 text-xs">
      <div class="rounded bg-slate-800/60 border border-slate-700 px-2 py-1">
        <span class="text-slate-400">Mean</span>
        <span class="font-mono text-emerald-300 ml-1">{result.mean_thrust_n.toFixed(4)} N</span>
      </div>
      <div class="rounded bg-slate-800/60 border border-slate-700 px-2 py-1">
        <span class="text-slate-400">Peak</span>
        <span class="font-mono text-sky-300 ml-1">{result.peak_thrust_n.toFixed(4)} N</span>
      </div>
      <div class="rounded bg-slate-800/60 border border-slate-700 px-2 py-1">
        <span class="text-slate-400">Min</span>
        <span class="font-mono text-rose-300 ml-1">{result.min_thrust_n.toFixed(4)} N</span>
      </div>
      <div class="rounded bg-slate-800/60 border border-slate-700 px-2 py-1">
        <span class="text-slate-400">Ripple</span>
        <span class="font-mono text-amber-300 ml-1">{result.ripple_pct.toFixed(1)}%</span>
      </div>
    </div>
  {/if}
</div>
