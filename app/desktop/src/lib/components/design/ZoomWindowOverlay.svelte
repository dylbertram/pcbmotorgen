<script lang="ts">
  let { onFit, onCancel }: { onFit: (a: [number, number], b: [number, number]) => void; onCancel: () => void } = $props();
  let start = $state<[number, number] | null>(null);
  let cursor = $state<[number, number] | null>(null);
  let width = $state(1), height = $state(1);
  const rectangle = $derived(start && cursor ? { x: Math.min(start[0], cursor[0]), y: Math.min(start[1], cursor[1]), width: Math.abs(start[0] - cursor[0]), height: Math.abs(start[1] - cursor[1]) } : null);
  function at(event: MouseEvent | PointerEvent): [number, number] {
    const rect = event.currentTarget instanceof Element ? event.currentTarget.getBoundingClientRect() : null;
    return rect ? [Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))] : [0, 0];
  }
  function choose(event: MouseEvent) {
    event.stopPropagation();
    if (!event.detail) return;
    const point = at(event);
    if (!start) { start = point; cursor = point; }
    else if (Math.abs(point[0] - start[0]) * width >= 4 && Math.abs(point[1] - start[1]) * height >= 4) onFit(start, point);
  }
</script>

<svelte:window onkeydown={(event) => { if (event.key === "Escape") { event.preventDefault(); event.stopImmediatePropagation(); onCancel(); } }} />
<button type="button" aria-label="Pick zoom window corners" class="zoom-window absolute inset-0 z-10 cursor-crosshair touch-none"
  bind:clientWidth={width} bind:clientHeight={height} onclick={choose}
  onpointerdown={event => event.stopPropagation()} onpointerup={event => event.stopPropagation()}
  onpointermove={event => { event.stopPropagation(); cursor = at(event); }}
  ontouchstart={event => event.stopPropagation()} ontouchmove={event => event.stopPropagation()} ontouchend={event => event.stopPropagation()}
  onwheel={event => { event.preventDefault(); event.stopPropagation(); }}>
  {#if rectangle}
    <svg class="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <rect x={rectangle.x * 100} y={rectangle.y * 100} width={rectangle.width * 100} height={rectangle.height * 100} fill="#34d399" fill-opacity=".12" stroke="#34d399" stroke-width="1.5" vector-effect="non-scaling-stroke" />
    </svg>
  {/if}
  <span role="status" class="pointer-events-none absolute left-1/2 top-12 -translate-x-1/2 whitespace-nowrap rounded bg-slate-900/95 px-3 py-2 text-xs text-emerald-200">{start ? "Choose the opposite corner" : "Choose the first corner"} · Esc to cancel</span>
</button>
