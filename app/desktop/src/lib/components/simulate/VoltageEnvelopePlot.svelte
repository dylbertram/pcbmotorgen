<script lang="ts">
  import type { DriveAnalysis } from "../../types";
  import { createLinearScale, ticks, polyline } from "../../chart";

  let { analysis }: { analysis: DriveAnalysis } = $props();

  const W = 520;
  const H = 200;
  const PAD_L = 40;
  const PAD_R = 16;
  const PAD_T = 12;
  const PAD_B = 32;

  let plot = $derived.by(() => {
    const pts = analysis.speed_curve;
    if (pts.length < 2) return null;
    const xs = pts.map((p) => p.speed_m_s);
    const ys = pts.map((p) => p.required_v);
    const maxX = Math.max(...xs);
    const maxY = Math.max(analysis.bus_voltage_v * 1.08, Math.min(Math.max(...ys), analysis.bus_voltage_v * 2.5));
    const sx = createLinearScale(0, maxX, PAD_L, W - PAD_L - PAD_R);
    const sy = createLinearScale(0, maxY, H - PAD_B, -(H - PAD_T - PAD_B));
    const clipped = ys.map((y) => Math.min(y, maxY));
    // Shade the speeds the bus cannot reach at full current.
    const vmax = analysis.max_speed_m_s;
    return {
      sx,
      sy,
      maxX,
      line: polyline(sx, sy, xs, clipped),
      area: `${sx(0)},${sy(0)} ${polyline(sx, sy, xs, clipped)} ${sx(maxX)},${sy(0)}`,
      xTicks: ticks(0, maxX, 5, sx),
      yTicks: ticks(0, maxY, 5, sy),
      vmax: vmax !== null && vmax < maxX ? vmax : null,
    };
  });
</script>

<figure class="min-w-0">
  <svg
    viewBox="0 0 {W} {H}"
    class="h-auto w-full"
    role="img"
    aria-label="Required line-to-line voltage versus mover speed at the target phase current, against the usable bus voltage"
  >
    {#if plot}
      {#each plot.yTicks as t (t.v)}
        <line x1={PAD_L} y1={t.pos} x2={W - PAD_R} y2={t.pos} stroke="#1e293b" stroke-width="0.6" />
        <text x={PAD_L - 6} y={t.pos + 3} text-anchor="end" class="fill-slate-500" style="font-size:9px">{t.v.toFixed(1)}</text>
      {/each}
      {#each plot.xTicks as t (t.v)}
        <text x={t.pos} y={H - PAD_B + 13} text-anchor="middle" class="fill-slate-500" style="font-size:9px">{t.v.toFixed(2)}</text>
      {/each}

      {#if plot.vmax !== null}
        <rect
          x={plot.sx(plot.vmax)}
          y={PAD_T}
          width={W - PAD_R - plot.sx(plot.vmax)}
          height={H - PAD_T - PAD_B}
          fill="#f43f5e"
          fill-opacity="0.07"
        />
      {/if}

      <polygon points={plot.area} fill="#38bdf8" fill-opacity="0.08" />
      <polyline points={plot.line} fill="none" stroke="#38bdf8" stroke-width="1.8" />

      <!-- usable and full bus -->
      <line x1={PAD_L} y1={plot.sy(analysis.available_voltage_v)} x2={W - PAD_R} y2={plot.sy(analysis.available_voltage_v)} stroke="#34d399" stroke-width="1.2" stroke-dasharray="5 3" />
      <text x={W - PAD_R - 2} y={plot.sy(analysis.available_voltage_v) - 4} text-anchor="end" class="fill-emerald-300" style="font-size:9px">usable {analysis.available_voltage_v.toFixed(1)} V</text>
      <line x1={PAD_L} y1={plot.sy(analysis.bus_voltage_v)} x2={W - PAD_R} y2={plot.sy(analysis.bus_voltage_v)} stroke="#64748b" stroke-width="1" />
      <text x={W - PAD_R - 2} y={plot.sy(analysis.bus_voltage_v) - 4} text-anchor="end" class="fill-slate-400" style="font-size:9px">bus {analysis.bus_voltage_v.toFixed(1)} V</text>

      <!-- target speed -->
      {#if analysis.target_speed_m_s <= plot.maxX}
        <line x1={plot.sx(analysis.target_speed_m_s)} y1={PAD_T} x2={plot.sx(analysis.target_speed_m_s)} y2={H - PAD_B} stroke="#f59e0b" stroke-width="1" stroke-dasharray="3 3" />
        <text x={plot.sx(analysis.target_speed_m_s) + 4} y={PAD_T + 9} class="fill-amber-300" style="font-size:9px">target</text>
      {/if}

      <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={H - PAD_B} stroke="#475569" />
      <line x1={PAD_L} y1={H - PAD_B} x2={W - PAD_R} y2={H - PAD_B} stroke="#475569" />
      <text x={(W + PAD_L) / 2} y={H - 4} text-anchor="middle" class="fill-slate-400" style="font-size:10px">Mover speed (m/s)</text>
      <text x={11} y={(H - PAD_B) / 2} text-anchor="middle" transform="rotate(-90 11 {(H - PAD_B) / 2})" class="fill-slate-400" style="font-size:10px">V line-to-line</text>
    {/if}
  </svg>
  <figcaption class="mt-1 text-xs text-slate-400">
    Voltage needed to keep {analysis.phase_current_a.toFixed(2)} A flowing as the mover speeds up.
    {#if analysis.max_speed_m_s !== null}
      The current starts to collapse past <span class="font-mono text-slate-200">{analysis.max_speed_m_s.toFixed(2)} m/s</span>.
    {:else}
      Back-EMF is left out until the thrust sweep finishes.
    {/if}
  </figcaption>
</figure>
