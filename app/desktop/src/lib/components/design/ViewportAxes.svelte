<script lang="ts">
  import { viewportAxes, type AxisCamera, type AxisView } from "../../viewportAxes";
  let { view, camera = null }: { view: AxisView; camera?: AxisCamera | null } = $props();
  const axes = $derived(viewportAxes(view, camera));
</script>

<svg viewBox="0 0 80 80" role="img" aria-label="Viewport axes: X travel, Y across board, Z up" class="viewport-axes" data-view={view}>
  <title>Board XYZ orientation</title>
  {#each axes as axis (axis.name)}
    <g data-axis={axis.name} data-direction={JSON.stringify([axis.x, axis.y, axis.depth])} style:color={`var(--axis-${axis.name.toLowerCase()})`} fill="currentColor" stroke="currentColor">
      {#if Math.hypot(axis.x, axis.y) < .08}
        <circle cx="40" cy="40" r="3" fill={axis.depth > 0 ? "currentColor" : "none"} />
        <text x="51" y="44">{axis.name}</text>
      {:else}
        <line x1="40" y1="40" x2={40 + axis.x * 25} y2={40 + axis.y * 25} opacity={axis.depth < 0 ? .55 : 1} />
        <text x={40 + axis.x * 34} y={44 + axis.y * 34}>{axis.name}</text>
      {/if}
    </g>
  {/each}
</svg>

<style>
  .viewport-axes { --axis-x: #f87171; --axis-y: #34d399; --axis-z: #60a5fa; display: block; width: 5rem; height: 5rem; pointer-events: none; }
  :global(:root[data-theme="light"]) .viewport-axes { --axis-x: #b91c1c; --axis-y: #047857; --axis-z: #1d4ed8; }
  line, circle { stroke-width: 1.25; }
  text { stroke: none; text-anchor: middle; font: 600 .6875rem var(--font-sans, sans-serif); }
</style>
