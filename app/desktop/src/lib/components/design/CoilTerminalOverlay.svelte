<script lang="ts">
  import type { CadGeometry, CadTerminal } from "../../types";
  import type { WorldTransform } from "../../chart";
  import type { CoilTerminalTool } from "../../utils/coilTerminalTool.svelte";
  import { terminalDescription } from "../../cadTerminals";
  let { geometry, tool, transform, panX, panY, width, height, isVisible, worldScale = 1e-3 }: {
    geometry: CadGeometry;
    tool?: CoilTerminalTool;
    transform: WorldTransform;
    panX: number;
    panY: number;
    width: number;
    height: number;
    isVisible: (coil: string, layer: number) => boolean;
    worldScale?: number;
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

<div class="pointer-events-none absolute inset-0 overflow-hidden" role="group" aria-label="Coil terminal markers">
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
  {#each labels as label (`${label.coil}:${label.role}`)}
    <span class="absolute -translate-x-1/2 -translate-y-1/2" style={location(label.point)}>
      <span role="img" aria-label={`Coil ${label.coil} ${label.role}, ${terminalDescription(label.point)}${label.draft ? ", preview" : ""}`} class="block h-3 w-3 rounded-full border-2 border-slate-950" style:background-color={label.role === "IN" ? "#34d399" : "#fbbf24"}></span>
      {#if label.draft}
        <button type="button" class="pointer-events-auto absolute {label.role === 'IN' ? 'bottom-4' : 'top-4'} left-0 whitespace-nowrap rounded border border-slate-600 bg-slate-950/95 px-1.5 py-0.5 text-[10px] font-semibold text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-400" aria-label={`Change ${label.role} for coil ${label.coil}`} title={`Choose a different ${label.role} endpoint in the preview.`}
          onpointerdown={pointerDown} onpointermove={pointerMove} onpointerup={pointerUp}
           onpointercancel={(event) => { if (event.pointerType !== "touch") event.stopPropagation(); downs.delete(event.pointerId); suppressClick = true; }}
          onclick={(event) => { event.stopPropagation(); if (event.detail === 0 || !suppressClick) tool?.change(label.role === "IN" ? "input" : "output"); }}>{label.coil} {label.role} · L{label.point.layer}</button>
      {:else}
        <span class="absolute {label.role === 'IN' ? 'bottom-4' : 'top-4'} left-0 whitespace-nowrap rounded border border-slate-600 bg-slate-950/95 px-1.5 py-0.5 text-[10px] font-semibold text-slate-100">{label.coil} {label.role} · L{label.point.layer}</span>
      {/if}
    </span>
  {/each}
</div>
