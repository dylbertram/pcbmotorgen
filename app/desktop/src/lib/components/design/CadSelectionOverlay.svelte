<script lang="ts">
  import type { CadGeometry, CadPoint } from "../../types";
  import type { WorldTransform } from "../../chart";
  import type { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";
  import { selectableTraces } from "../../cadSelection";
  let { geometry, tool, transform, panX, panY, width, height, worldScale = 1, isVisible, disabled = false }: {
    geometry: CadGeometry; tool: CadSelectionTool; transform: WorldTransform; panX: number; panY: number;
    width: number; height: number; worldScale?: number; isVisible: (coil: string, layer: number) => boolean; disabled?: boolean;
  } = $props();
  let svg: HTMLDivElement;
  const uid = $props.id();
  let focusedIndex = $state(-1);
  let drag = $state<{ id: number; start: CadPoint; end: CadPoint; clientX: number; clientY: number; shift: boolean } | null>(null);
  let allTraces = $derived(selectableTraces(geometry));
  let traces = $derived(allTraces.filter((t) => isVisible(t.net, t.layer)));
  let selectedIds = $derived(new Set(tool.selected));
  let scale = $derived(transform.s * worldScale);
  let box = $derived(drag && tool.mode === "box" ? { minX: Math.min(drag.start.x, drag.end.x), minY: Math.min(drag.start.y, drag.end.y), maxX: Math.max(drag.start.x, drag.end.x), maxY: Math.max(drag.start.y, drag.end.y) } : null);
  function point(e: PointerEvent): CadPoint {
    const rect = svg.getBoundingClientRect();
    return { x: ((e.clientX - rect.left) / rect.width * width - transform.tx - panX) / scale, y: -((e.clientY - rect.top) / rect.height * height - transform.ty - panY) / scale };
  }
  function down(e: PointerEvent) {
    if (e.button !== 0 || disabled || tool.mode === "pan") return;
    e.stopPropagation();
    svg.focus();
    if (drag) { drag = null; return; }
    drag = { id: e.pointerId, start: point(e), end: point(e), clientX: e.clientX, clientY: e.clientY, shift: e.shiftKey };
    svg.setPointerCapture(e.pointerId);
  }
  function move(e: PointerEvent) { e.stopPropagation(); if (drag?.id === e.pointerId) drag.end = point(e); }
  function up(e: PointerEvent) {
    e.stopPropagation();
    if (!drag || drag.id !== e.pointerId) return;
    const moved = Math.hypot(e.clientX - drag.clientX, e.clientY - drag.clientY) > 4;
    if (tool.mode === "box" && box && moved) tool.selectBox(box, traces, drag.shift);
    else if (!moved) tool.pick(point(e), traces, Math.max(geometry.trace_width_mm / 2, 7 * width / svg.getBoundingClientRect().width / scale), drag.shift);
    drag = null;
  }
</script>

<div bind:this={svg} class="absolute inset-0 h-full w-full overflow-hidden" style:pointer-events={!disabled && tool.mode !== "pan" ? "auto" : "none"} style:cursor={tool.mode !== "pan" ? "crosshair" : undefined}
  role="listbox" aria-label="Segment selection preview" aria-hidden={disabled || tool.mode === "pan"} aria-multiselectable="true" aria-describedby={`${uid}-help`} aria-activedescendant={traces[focusedIndex] ? `${uid}-${focusedIndex}` : undefined} tabindex={!disabled && tool.mode !== "pan" ? 0 : -1}
  onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={(e) => { e.stopPropagation(); drag = null; }} onlostpointercapture={() => { drag = null; }}
  ontouchstart={(e) => { if (tool.mode !== "pan") e.stopPropagation(); }} ontouchmove={(e) => { if (tool.mode !== "pan") e.stopPropagation(); }} ontouchend={(e) => { if (tool.mode !== "pan") e.stopPropagation(); }}
  onkeydown={(e) => {
    if (e.key === "Escape") { e.stopPropagation(); tool.clear(); drag = null; }
    if ((e.ctrlKey || e.metaKey) && e.key === "a") { e.preventDefault(); tool.selected = traces.map((t) => t.id); }
    if (e.key.startsWith("Arrow") && traces.length) { e.preventDefault(); focusedIndex = (focusedIndex + (e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1) + traces.length) % traces.length; }
    if (e.key === "Enter" && traces[focusedIndex]) { e.preventDefault(); tool.pickTrace(traces[focusedIndex].id, traces, e.shiftKey); }
  }}>
  <span id={`${uid}-help`} class="sr-only">Use arrow keys to focus a segment, then Enter to select. Shift-Enter toggles selection. Escape clears selection.</span>
  {#each traces as trace, i (trace.id)}<span role="option" id={`${uid}-${i}`} aria-selected={selectedIds.has(trace.id)} class="sr-only">Segment {i + 1}, coil {trace.net}, layer {trace.layer}</span>{/each}
  <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" class="pointer-events-none block h-full w-full" aria-hidden="true">
  <g transform={`matrix(${scale} 0 0 ${-scale} ${transform.tx + panX} ${transform.ty + panY})`}>
    {#each traces.filter((t) => selectedIds.has(t.id)) as trace (trace.id)}
      <path d={trace.path} fill="none" stroke="#f8fafc" stroke-width={geometry.trace_width_mm + 3 / scale} stroke-linecap="round" />
      <path d={trace.path} fill="none" stroke="#facc15" stroke-width={geometry.trace_width_mm + 1 / scale} stroke-linecap="round" />
    {/each}
    {#if traces[focusedIndex] && tool.mode !== "pan"}<path d={traces[focusedIndex].path} fill="none" stroke="#38bdf8" stroke-width={geometry.trace_width_mm + 2 / scale} stroke-dasharray={`${3 / scale} ${2 / scale}`} />{/if}
    {#if box}<rect x={box.minX} y={box.minY} width={box.maxX - box.minX} height={box.maxY - box.minY} fill={tool.boxAction === "remove" ? "#fb718522" : "#34d39922"} stroke={tool.boxAction === "remove" ? "#fb7185" : "#34d399"} stroke-width={1 / scale} stroke-dasharray={tool.crossing ? `${4 / scale} ${3 / scale}` : undefined} />{/if}
  </g>
  </svg>
</div>
