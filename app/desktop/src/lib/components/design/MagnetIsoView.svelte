<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import { isoBoxPath, isoCenter, isoProject, isoVisibleFaces } from "../../geometry";

  let { config }: { config: ConfigStore } = $props();
  const W = 360;
  const H = 176;
  const dimensions = $derived({ length: config.magnet_width_mm, width: config.magnet_cross_width_mm, totalHeight: config.magnet_height_mm });
  const arrayDimensions = $derived({ ...dimensions, length: config.mover_span_mm });
  const scale = $derived(Math.min(320 / (arrayDimensions.length + 0.45 * dimensions.width), 106 / (dimensions.totalHeight + 0.45 * dimensions.width)));
  // All three axes use the same scale. Unlike the assembly view, Z is not exaggerated.
  const project = (x: number, y: number, z: number, cx: number, cy: number): [number, number] => isoProject(x, y, z, cx, cy, scale, scale);
  const center = $derived(isoCenter(arrayDimensions, W, H - 48, project));
  const box = $derived(isoBoxPath(0, 0, 0, dimensions.length, dimensions.width, dimensions.totalHeight, center.cx, center.cy, project));
  const magnets = $derived(Array.from({ length: config.magnet_count }, (_, index) => {
    const x = index * config.pole_pitch_mm;
    return { index, x, faces: isoVisibleFaces(isoBoxPath(x, 0, 0, dimensions.length, dimensions.width, dimensions.totalHeight, center.cx, center.cy, project).corners) };
  }).reverse());
  const edges = $derived([
    { axis: "X", a: box.corners[3], b: box.corners[2], value: dimensions.length, color: "#ef4444" },
    { axis: "Y", a: box.corners[0], b: box.corners[3], value: dimensions.width, color: "#22c55e" },
    { axis: "Z", a: box.corners[2], b: box.corners[6], value: dimensions.totalHeight, color: "#3b82f6" },
  ]);
</script>

<svg viewBox="0 0 {W} {H}" class="h-44 w-full" role="img" aria-label="Magnet array, three-quarter view at true scale">
  <title>{config.magnet_count} magnets, {config.magnet_gap_mm.toFixed(1)} mm gap. Each magnet: X {dimensions.length.toFixed(1)} mm, Y {dimensions.width.toFixed(1)} mm, Z {dimensions.totalHeight.toFixed(1)} mm. All axes use the same scale.</title>
  {#each magnets as magnet (magnet.index)}
    <g data-solid="magnet" data-index={magnet.index} data-x-mm={magnet.x} data-length-mm={dimensions.length} stroke="#10b981" stroke-width="0.8" stroke-linejoin="round">
      <polygon points={magnet.faces.end} class="magnet-end" />
      <polygon points={magnet.faces.front} class="magnet-front" />
      <polygon points={magnet.faces.top} class="magnet-top" />
    </g>
  {/each}
  {#each edges as edge, i (edge.axis)}
    <g data-axis={edge.axis}>
      <line x1={edge.a[0]} y1={edge.a[1]} x2={edge.b[0]} y2={edge.b[1]} stroke={edge.color} stroke-width="1.4" />
      <text x={12 + i * 86} y="144" class="fill-slate-300" style="font-size:10px">{edge.axis} {edge.value.toFixed(1)} mm</text>
    </g>
  {/each}
  <text x="270" y="144" data-gap class="fill-slate-300" style="font-size:10px">Gap {config.magnet_gap_mm.toFixed(1)} mm</text>
  <text x="180" y="165" text-anchor="middle" class="fill-slate-400" style="font-size:10px">{config.magnet_count} magnets · {config.mover_span_mm.toFixed(1)} mm span</text>
</svg>

<style>
  .magnet-end { fill: #064e3b; }
  .magnet-front { fill: #065f46; }
  .magnet-top { fill: #047857; }
  :global(:root[data-theme="light"]) .magnet-end { fill: #059669; }
  :global(:root[data-theme="light"]) .magnet-front { fill: #34d399; }
  :global(:root[data-theme="light"]) .magnet-top { fill: #a7f3d0; }
</style>
