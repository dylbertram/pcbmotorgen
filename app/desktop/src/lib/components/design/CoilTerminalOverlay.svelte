<script lang="ts">
  import type { CadGeometry, CadTerminal } from "../../types";
  import type { WorldTransform } from "../../chart";
  import type { CoilTerminalTool } from "../../utils/coilTerminalTool.svelte";
  import { terminalDescription } from "../../cadTerminals";
  import { layoutTerminalMarkers } from "../../terminalMarkerLayout";
  let { geometry, tool, transform, panX, panY, width, height, isVisible, worldScale = 1e-3, showMarkers = true, rightInset = 0 }: {
    geometry: CadGeometry;
    tool?: CoilTerminalTool;
    transform: WorldTransform;
    panX: number;
    panY: number;
    width: number;
    height: number;
    isVisible: (coil: string, layer: number) => boolean;
    worldScale?: number;
    showMarkers?: boolean;
    rightInset?: number;
  } = $props();
  function location(point: CadTerminal): string {
    const x = point.position.x * worldScale * transform.s + transform.tx + panX;
    const y = -point.position.y * worldScale * transform.s + transform.ty + panY;
    return `left:${x / width * 100}%;top:${y / height * 100}%;`;
  }
  let candidates = $derived(tool?.active && (tool.step === "input" || tool.step === "output")
    ? tool.candidates.filter((p) => p.layer === tool.layer && isVisible(tool.coil, p.layer)) : []);
  let labels = $derived.by(() => {
    const result: { coil: string; role: "IN" | "OUT"; point: CadTerminal; draft: boolean }[] = [];
    for (const [coil, terminals] of Object.entries(geometry.coil_terminals ?? {})) {
      if (tool?.active && tool.coil === coil) continue;
      result.push({ coil, role: "IN", point: terminals.input, draft: false }, { coil, role: "OUT", point: terminals.output, draft: false });
    }
    if (tool?.active && tool.coil) {
      if (tool.input) result.push({ coil: tool.coil, role: "IN", point: tool.input, draft: true });
      if (tool.output) result.push({ coil: tool.coil, role: "OUT", point: tool.output, draft: true });
    }
    return result.filter((label) => isVisible(label.coil, label.point.layer));
  });
  let renderedWidth = $state(0);
  let renderedHeight = $state(0);
  const markerId = $props.id();
  let callouts = $derived(layoutTerminalMarkers(labels.map(({ point }) => ({
    x: (point.position.x * worldScale * transform.s + transform.tx + panX) / width * renderedWidth,
    y: (-point.position.y * worldScale * transform.s + transform.ty + panY) / height * renderedHeight,
  })), Math.max(140, renderedWidth - rightInset), renderedHeight));
  const downs = new Map<number, { x: number; y: number; moved: boolean }>();
  let suppressClick = false;
  function pointerDown(event: PointerEvent): void {
    if (event.button !== 0) return;
    if (event.pointerType !== "touch") event.stopPropagation();
    suppressClick = false;
    downs.set(event.pointerId, { x: event.clientX, y: event.clientY, moved: false });
    if (downs.size > 1) for (const down of downs.values()) down.moved = true;
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }
  function pointerMove(event: PointerEvent): void {
    if (event.pointerType !== "touch") event.stopPropagation();
    const down = downs.get(event.pointerId);
    if (down && Math.hypot(event.clientX - down.x, event.clientY - down.y) > 6) down.moved = true;
  }
  function pointerUp(event: PointerEvent): void {
    if (event.pointerType !== "touch") event.stopPropagation();
    const down = downs.get(event.pointerId);
    suppressClick = !down || down.moved || Math.hypot(event.clientX - down.x, event.clientY - down.y) > 6;
    downs.delete(event.pointerId);
  }
</script>

<svelte:window ontouchstart={(event) => {
  if (tool?.active && event.touches.length > 1) {
    suppressClick = true;
    for (const down of downs.values()) down.moved = true;
  }
}} />

<div bind:clientWidth={renderedWidth} bind:clientHeight={renderedHeight} class="pointer-events-none absolute inset-0 overflow-hidden" role="group" aria-label="Coil terminal markers">
  {#each candidates as point (`${point.layer}:${point.position.x}:${point.position.y}`)}
    <button type="button" class="pointer-events-auto absolute flex h-5 w-5 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full focus:outline-none focus:ring-2 focus:ring-emerald-400" style={location(point)}
      aria-label={`Endpoint coil ${tool?.coil}, ${terminalDescription(point)}`}
      title={terminalDescription(point)}
      onpointerdown={pointerDown} onpointermove={pointerMove} onpointerup={pointerUp}
      onpointercancel={(event) => { if (event.pointerType !== "touch") event.stopPropagation(); downs.delete(event.pointerId); suppressClick = true; }}
      onclick={(event) => { event.stopPropagation(); if (event.detail === 0 || !suppressClick) tool?.pick(point); }}>
      <span class="h-2.5 w-2.5 rounded-full border border-emerald-200 bg-slate-950/90"></span>
    </button>
  {/each}
  {#if showMarkers && renderedWidth && renderedHeight}
    <svg class="absolute inset-0 h-full w-full overflow-hidden" viewBox={`0 0 ${renderedWidth} ${renderedHeight}`} aria-label="IN/OUT direction arrows" role="group">
      <defs>
        {#each ["IN", "OUT"] as role (role)}
          <marker id={`${markerId}-${role}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse" markerUnits="userSpaceOnUse"><path d="M 1 1 L 9 5 L 1 9 Z" fill={role === "IN" ? "#34d399" : "#fbbf24"} stroke="#020617" stroke-width="1" /></marker>
        {/each}
      </defs>
      {#each labels as label, index (`${label.coil}:${label.role}`)}
        {@const p = callouts[index]}
        {@const color = label.role === "IN" ? "#34d399" : "#fbbf24"}
        {@const lx = p.labelX > p.x ? p.labelX : p.labelX + 132}
        <g role="img" aria-label={`Coil ${label.coil} ${label.role}, ${terminalDescription(label.point)}${label.draft ? ", preview" : ""}`}>
          <title>{label.coil} {label.role} · {terminalDescription(label.point)}</title>
          <line x1={p.x} y1={p.y} x2={lx} y2={p.labelY + 12} stroke="#020617" stroke-width="6" />
          <line x1={p.x} y1={p.y} x2={lx} y2={p.labelY + 12} stroke={color} stroke-width="2" marker-start={label.role === "IN" ? `url(#${markerId}-IN)` : undefined} marker-end={label.role === "OUT" ? `url(#${markerId}-OUT)` : undefined} />
          <circle cx={p.x} cy={p.y} r="3" fill={color} stroke="#020617" stroke-width="1" />
          <rect x={p.labelX} y={p.labelY} width="132" height="24" rx="4" fill="#020617" stroke={color} />
          <text x={p.labelX + 8} y={p.labelY + 16} fill={color} font-size="11" font-weight="600" textLength={label.coil.length > 10 ? 116 : undefined} lengthAdjust="spacingAndGlyphs">{label.coil} {label.role} · L{label.point.layer + 1}</text>
        </g>
      {/each}
    </svg>
  {/if}
</div>
