<script lang="ts">
  import type { SensorStore } from "../../stores/sensor.svelte";

  let { store }: { store: SensorStore } = $props();

  let geometry = $derived(store.geometry);
  let viewBox = $derived.by(() => {
    if (!geometry) return "-12 -9 144 18";
    const [minX, minY, maxX, maxY] = geometry.board_bounds_mm;
    const pad = Math.max(1, Math.max(maxX - minX, maxY - minY) * 0.025);
    return `${minX - pad} ${minY - pad} ${maxX - minX + 2 * pad} ${maxY - minY + 2 * pad}`;
  });

  function colorFor(net: string): string {
    if (net === "CL1") return "#fbbf24";
    if (net === "CL2") return "#22d3ee";
    return "#c084fc";
  }
</script>

<section
  class="overflow-hidden rounded-lg border border-slate-700 bg-slate-800/40"
  aria-labelledby="sensor-preview-title"
>
  <div class="flex items-center justify-between gap-3 border-b border-slate-700 px-3 py-2">
    <div>
      <h2 id="sensor-preview-title" class="text-xs font-semibold uppercase tracking-wider text-slate-200">
        Induction sensor preview
      </h2>
      <p class="mt-0.5 text-[11px] text-slate-500">Top-down · F.Cu and B.Cu overlaid</p>
    </div>
    {#if store.loading}
      <span class="text-[11px] text-amber-300" role="status">Generating…</span>
    {:else if geometry}
      <span class="font-mono text-[11px] text-slate-400">
        {geometry.nets.reduce((n, net) => n + net.segments.length, 0)} tracks
      </span>
    {/if}
  </div>

  {#if store.error}
    <div class="m-3 rounded-md border border-rose-500/50 bg-rose-500/10 px-3 py-2 text-xs text-rose-200" role="alert">
      {store.error}
    </div>
  {/if}

  <svg
    class="block h-auto max-h-[360px] min-h-[220px] w-full bg-slate-950/70"
    viewBox={viewBox}
    preserveAspectRatio="xMidYMid meet"
    role="img"
    aria-label="Generated two-layer induction position sensor traces"
  >
    <title>Induction position sensor copper layout</title>
    {#if geometry}
      {#each geometry.nets as net (net.name)}
        <g fill="none" stroke={colorFor(net.name)} stroke-width={net.trace_width_mm} stroke-linecap="round" stroke-linejoin="round">
          {#each net.segments as segment, index (`${net.name}-${index}`)}
            <line
              x1={segment.start.x}
              y1={segment.start.y}
              x2={segment.end.x}
              y2={segment.end.y}
              opacity={segment.layer === 0 ? 0.95 : 0.58}
              stroke-dasharray={segment.layer === 1 ? "0.8 0.55" : undefined}
            />
          {/each}
        </g>
        {#each net.vias as via, index (`${net.name}-via-${index}`)}
          <circle
            cx={via.position.x}
            cy={via.position.y}
            r={net.via_size_mm / 2}
            fill="#0f172a"
            stroke={colorFor(net.name)}
            stroke-width="0.12"
          />
        {/each}
      {/each}
      {#each geometry.terminal_markers as [net, terminal], index (`terminal-${index}`)}
        <circle
          cx={terminal.x}
          cy={terminal.y}
          r="0.38"
          fill="#0f172a"
          stroke={colorFor(net)}
          stroke-width="0.16"
        />
      {/each}
    {:else if !store.error}
      <text x="0" y="0" text-anchor="middle" fill="#94a3b8" font-size="1.8">
        {store.loading ? "Generating sensor geometry…" : "Sensor geometry unavailable"}
      </text>
    {/if}
  </svg>

  <div class="flex flex-wrap gap-x-4 gap-y-1 border-t border-slate-700 px-3 py-2 text-[11px] text-slate-400">
    {#each [{ name: "CL1", label: "Cosine receiver" }, { name: "CL2", label: "Sine receiver" }, { name: "OSC", label: "Transmitter" }] as item (item.name)}
      {#if geometry?.nets.some((net) => net.name === item.name)}
        <span class="inline-flex items-center gap-1.5">
          <span class="h-2 w-2 rounded-full" style:background-color={colorFor(item.name)}></span>
          {item.label}
        </span>
      {/if}
    {/each}
    <span class="ml-auto">dashed: B.Cu · solid: F.Cu</span>
  </div>
</section>
