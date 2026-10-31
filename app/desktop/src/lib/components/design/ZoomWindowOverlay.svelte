<script lang="ts">
  let { onFit, onCancel }: { onFit: (a: [number, number], b: [number, number]) => void; onCancel: () => void } = $props();
  let start = $state<[number, number] | null>(null);
  let cursor = $state<[number, number] | null>(null);
  let dragging = $state(false);
  let press: { id: number; point: [number, number]; anchor: [number, number] | null } | null = null;
  let ignoreClick = false;
  let width = $state(1), height = $state(1);
  const rectangle = $derived(start && cursor ? { x: Math.min(start[0], cursor[0]), y: Math.min(start[1], cursor[1]), width: Math.abs(start[0] - cursor[0]), height: Math.abs(start[1] - cursor[1]) } : null);
  function at(event: MouseEvent | PointerEvent): [number, number] {
    const rect = event.currentTarget instanceof Element ? event.currentTarget.getBoundingClientRect() : null;
    return rect ? [Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))] : [0, 0];
  }
  function choose(event: MouseEvent) {
    event.stopPropagation();
    if (ignoreClick) { ignoreClick = false; return; }
    if (!event.detail) return;
    const point = at(event);
    if (!start) { start = point; cursor = point; }
    else fit(point);
  }
  function fit(point: [number, number]) {
    if (start && Math.abs(point[0] - start[0]) * width >= 4 && Math.abs(point[1] - start[1]) * height >= 4) onFit(start, point);
  }
  function begin(event: PointerEvent) {
    event.stopPropagation();
    if (!event.isPrimary || event.button !== 0 || press) return;
    ignoreClick = false;
    press = { id: event.pointerId, point: at(event), anchor: start };
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }
  function move(event: PointerEvent) {
    event.stopPropagation();
    if (press && press.id !== event.pointerId) return;
    cursor = at(event);
    if (press && Math.hypot((cursor[0] - press.point[0]) * width, (cursor[1] - press.point[1]) * height) >= 4) {
      dragging = true;
      start ??= press.point;
    }
  }
  function release(event: PointerEvent) {
    event.stopPropagation();
    const node = event.currentTarget as HTMLElement;
    if (node.hasPointerCapture(event.pointerId)) node.releasePointerCapture(event.pointerId);
  }
  function end(event: PointerEvent) {
    event.stopPropagation();
    if (!press || press.id !== event.pointerId) return;
    move(event);
    const wasDragging = dragging;
    press = null; dragging = false;
    release(event);
    if (wasDragging) { ignoreClick = true; fit(at(event)); }
  }
  function cancel(event: PointerEvent) {
    event.stopPropagation();
    if (!press || press.id !== event.pointerId) return;
    start = press.anchor; cursor = start;
    press = null; dragging = false; ignoreClick = false;
    release(event);
  }
</script>

<svelte:window onkeydown={(event) => { if (event.key === "Escape") { event.preventDefault(); event.stopImmediatePropagation(); onCancel(); } }} />
<button type="button" aria-label="Pick zoom window corners" class="zoom-window absolute inset-0 z-10 cursor-crosshair touch-none"
  bind:clientWidth={width} bind:clientHeight={height} onclick={choose}
  onpointerdown={begin} onpointerup={end} onpointermove={move} onpointercancel={cancel} onlostpointercapture={cancel}
  ontouchstart={event => event.stopPropagation()} ontouchmove={event => event.stopPropagation()} ontouchend={event => event.stopPropagation()}
  onwheel={event => { event.preventDefault(); event.stopPropagation(); }}>
  {#if rectangle}
    <svg class="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <rect x={rectangle.x * 100} y={rectangle.y * 100} width={rectangle.width * 100} height={rectangle.height * 100} fill="#34d399" fill-opacity=".12" stroke="#34d399" stroke-width="1.5" vector-effect="non-scaling-stroke" />
    </svg>
  {/if}
  <span role="status" class="pointer-events-none absolute left-1/2 top-12 w-max max-w-[calc(100%-1rem)] -translate-x-1/2 rounded bg-slate-900/95 px-3 py-2 text-center text-xs text-emerald-200">{dragging ? "Release to zoom" : start ? "Choose the opposite corner" : "Drag a window or click two corners"} · Esc to cancel</span>
</button>
