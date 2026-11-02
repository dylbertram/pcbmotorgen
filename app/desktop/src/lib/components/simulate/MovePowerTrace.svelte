<script lang="ts">
  import type { MovePowerSample } from "../../types/movePower";
  import { formatSi } from "../../format";

  let { samples, supply = false }: { samples: MovePowerSample[]; supply?: boolean } = $props();

  const W = 640, H = 150, LEFT = 46, RIGHT = 10, TOP = 10, BOTTOM = 24;

  let plot = $derived.by(() => {
    if (samples.length < 2) return null;
    const values = samples.map(s => supply ? (s.required_source_power_w ?? 0) : s.partial_dc_link_power_w);
    const t0 = samples[0].time_s, t1 = samples[samples.length - 1].time_s;
    const span = Math.max(t1 - t0, 1e-12);
    const max = Math.max(0, ...values);
    const min = Math.min(0, ...values);
    const range = Math.max(max - min, 1e-12);
    const x = (t: number) => LEFT + (t - t0) / span * (W - LEFT - RIGHT);
    const y = (v: number) => TOP + (max - v) / range * (H - TOP - BOTTOM);
    const line = values.map((v, i) => `${i ? "L" : "M"}${x(samples[i].time_s).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    const area = `${line} L${x(t1).toFixed(1)},${y(0).toFixed(1)} L${x(t0).toFixed(1)},${y(0).toFixed(1)} Z`;
    return { line, area, zeroY: y(0), max, min, x0: x(t0), x1: x(t1), t1 };
  });
</script>

{#if plot}
  <figure class="m-0">
    <svg viewBox="0 0 {W} {H}" class="h-36 w-full" role="img"
      aria-label={`Power during the move, peaking at ${formatSi(plot.max, "W")}`}>
      <line x1={plot.x0} x2={plot.x1} y1={plot.zeroY} y2={plot.zeroY} class="stroke-slate-600" stroke-width="1" />
      <path d={plot.area} class="fill-sky-500/15" />
      <path d={plot.line} class="fill-none stroke-sky-400" stroke-width="2" stroke-linejoin="round" />
      <text x={LEFT - 6} y={TOP + 8} text-anchor="end" class="fill-slate-400 text-[10px]">{formatSi(plot.max, "W")}</text>
      <text x={LEFT - 6} y={plot.zeroY + 3} text-anchor="end" class="fill-slate-400 text-[10px]">0 W</text>
      <text x={plot.x0} y={H - 6} text-anchor="start" class="fill-slate-400 text-[10px]">0 s</text>
      <text x={plot.x1} y={H - 6} text-anchor="end" class="fill-slate-400 text-[10px]">{formatSi(plot.t1, "s")}</text>
    </svg>
    {#if plot.min < 0}<figcaption class="text-xs text-amber-300">Negative values return energy to the link.</figcaption>{/if}
  </figure>
{/if}
