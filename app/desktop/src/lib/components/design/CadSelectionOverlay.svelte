<script lang="ts">
  import type { CadGeometry, CadPoint } from "../../types";
  import type { WorldTransform } from "../../chart";
  import type { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";
  import { selectableTraces } from "../../cadSelection";
  import SelectionAssignmentMenu from "./SelectionAssignmentMenu.svelte";
  let { geometry, tool, transform, panX, panY, width, height, worldScale = 1, isVisible, disabled = false }: {
    geometry: CadGeometry; tool: CadSelectionTool; transform: WorldTransform; panX: number; panY: number;
    width: number; height: number; worldScale?: number; isVisible: (coil: string, layer: number) => boolean; disabled?: boolean;
  } = $props();
  let svg: HTMLDivElement;
  const uid = $props.id();
  let focusedIndex = $state(-1);
  let multiTouch = false;
  const touchPointers = new Set<number>();
  let drag = $state<{ id: number; start: CadPoint; end: CadPoint; clientX: number; clientY: number; endClientX: number; endClientY: number; shift: boolean } | null>(null);
  let allTraces = $derived(selectableTraces(geometry));
  let traces = $derived(allTraces.filter((t) => isVisible(t.net, t.layer)));
  let selectedIds = $derived(new Set(tool.selected));
  let scale = $derived(transform.s * worldScale);
  let moved = $derived(drag ? Math.hypot(drag.endClientX - drag.clientX, drag.endClientY - drag.clientY) > 4 : false);
  let box = $derived(drag && moved ? { minX: Math.min(drag.start.x, drag.end.x), minY: Math.min(drag.start.y, drag.end.y), maxX: Math.max(drag.start.x, drag.end.x), maxY: Math.max(drag.start.y, drag.end.y) } : null);
  let crossing = $derived(tool.crossing === "direction" ? Boolean(drag && drag.end.x < drag.start.x) : tool.crossing);
  function point(e: PointerEvent): CadPoint {
    const rect = svg.getBoundingClientRect();
    return { x: ((e.clientX - rect.left) / rect.width * width - transform.tx - panX) / scale, y: -((e.clientY - rect.top) / rect.height * height - transform.ty - panY) / scale };
  }
  function down(e: PointerEvent) {
    if (e.button !== 0 || disabled) return;
    if (e.pointerType === "touch") {
      touchPointers.add(e.pointerId);
      if (touchPointers.size > 1) multiTouch = true;
      if (multiTouch) { drag = null; return; }
    } else e.stopPropagation();
    svg.focus();
    if (drag) { drag = null; return; }
    drag = { id: e.pointerId, start: point(e), end: point(e), clientX: e.clientX, clientY: e.clientY, endClientX: e.clientX, endClientY: e.clientY, shift: e.shiftKey };
    svg.setPointerCapture(e.pointerId);
  }
  function move(e: PointerEvent) { if (drag?.id === e.pointerId) { if (e.pointerType !== "touch") e.stopPropagation(); drag.end = point(e); drag.endClientX = e.clientX; drag.endClientY = e.clientY; } }
  function up(e: PointerEvent) {
    if (e.pointerType === "touch") {
      const wasMultiTouch = multiTouch;
      touchPointers.delete(e.pointerId);
      if (touchPointers.size === 0) multiTouch = false;
      if (wasMultiTouch) { drag = null; return; }
    }
    if (!drag || drag.id !== e.pointerId) return;
    if (e.pointerType !== "touch") e.stopPropagation();
    drag.end = point(e);
    drag.endClientX = e.clientX;
    drag.endClientY = e.clientY;
    const didMove = Math.hypot(e.clientX - drag.clientX, e.clientY - drag.clientY) > 4;
    if (box && didMove) { tool.anchor = null; tool.selectBox(box, traces, drag.shift, crossing); }
    else if (!didMove) tool.pick(point(e), traces, Math.max(geometry.trace_width_mm / 2, 7 * width / svg.getBoundingClientRect().width / scale), drag.shift);
    drag = null;
  }
</script>

<SelectionAssignmentMenu {geometry} {tool} {disabled} passthrough={disabled} triggerClass="absolute inset-0">
<div bind:this={svg} class="absolute inset-0 h-full w-full overflow-hidden" style:pointer-events={!disabled ? "auto" : "none"} style:cursor={!disabled ? "crosshair" : undefined}
  role="listbox" aria-label="Segment selection preview" aria-hidden={disabled} aria-multiselectable="true" aria-describedby={`${uid}-help`} aria-activedescendant={traces[focusedIndex] ? `${uid}-${focusedIndex}` : undefined} tabindex={!disabled ? 0 : -1}
  onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={(e) => { if (e.pointerType !== "touch" && drag?.id === e.pointerId) e.stopPropagation(); touchPointers.delete(e.pointerId); if (!touchPointers.size) multiTouch = false; drag = null; }} onlostpointercapture={(e) => { if (drag?.id === e.pointerId) drag = null; }}
  ontouchstart={(e) => { if (e.touches.length > 1) { drag = null; multiTouch = true; } }}
  ontouchend={(e) => { if (e.touches.length === 0) multiTouch = false; }} ontouchcancel={(e) => { drag = null; if (e.touches.length === 0) multiTouch = false; }}
  onkeydown={(e) => {
    if (e.key === "Escape" && (tool.selected.length || tool.anchor || drag)) { e.stopPropagation(); tool.clear(); drag = null; }
    if ((e.ctrlKey || e.metaKey) && e.key === "a") { e.preventDefault(); tool.selected = traces.map((t) => t.id); }
    if (e.key.startsWith("Arrow") && traces.length) { e.preventDefault(); focusedIndex = (focusedIndex + (e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1) + traces.length) % traces.length; }
    if (e.key === "Enter" && traces[focusedIndex]) { e.preventDefault(); tool.pickTrace(traces[focusedIndex].id, traces, e.shiftKey); }
  }}>
  <span id={`${uid}-help`} class="sr-only">Click a segment or drag a box to select. Drag right for contained selection, left for crossing selection. Two fingers pan and three-finger pinch zooms. Use arrow keys and Enter for keyboard selection. Shift adds. Escape clears selection.</span>
  {#each traces as trace, i (trace.id)}<span role="option" id={`${uid}-${i}`} aria-selected={selectedIds.has(trace.id)} class="sr-only">Segment {i + 1}, coil {trace.net}, layer {trace.layer}</span>{/each}
  <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" class="pointer-events-none block h-full w-full" aria-hidden="true">
  <g transform={`matrix(${scale} 0 0 ${-scale} ${transform.tx + panX} ${transform.ty + panY})`}>
    {#each traces.filter((t) => selectedIds.has(t.id)) as trace (trace.id)}
      <path d={trace.path} fill="none" stroke="#f8fafc" stroke-width={geometry.trace_width_mm + 3 / scale} stroke-linecap="round" />
      <path d={trace.path} fill="none" stroke="#facc15" stroke-width={geometry.trace_width_mm + 1 / scale} stroke-linecap="round" />
    {/each}
    {#if traces[focusedIndex]}<path d={traces[focusedIndex].path} fill="none" stroke="#38bdf8" stroke-width={geometry.trace_width_mm + 2 / scale} stroke-dasharray={`${3 / scale} ${2 / scale}`} />{/if}
    {#if box}<rect x={box.minX} y={box.minY} width={box.maxX - box.minX} height={box.maxY - box.minY} fill={tool.boxAction === "remove" ? "#fb718522" : "#34d39922"} stroke={tool.boxAction === "remove" ? "#fb7185" : "#34d399"} stroke-width={1 / scale} stroke-dasharray={crossing ? `${4 / scale} ${2 / scale}` : undefined} />{/if}
  </g>
  </svg>
</div>
</SelectionAssignmentMenu>
