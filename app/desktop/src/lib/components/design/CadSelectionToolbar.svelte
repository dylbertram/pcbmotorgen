<script lang="ts">
  import type { CadGeometry } from "../../types";
  import type { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";
  import { MousePointer2, Link, X, Undo2 } from "@lucide/svelte";
  import SelectionAssignmentMenu from "./SelectionAssignmentMenu.svelte";
  let { tool, geometry, onActivate = () => {}, disabled = false }: { tool: CadSelectionTool; geometry: CadGeometry; onActivate?: () => void; disabled?: boolean } = $props();
  const modes = [
    { id: "select", label: "Select", icon: MousePointer2, tip: "Click to select. Drag a box anytime. Shift adds. Two fingers or middle mouse pan; three-finger pinch zooms." },
    { id: "chain", label: "Chain", icon: Link, tip: "Chain: click the first and last segments of a connected chain. Vias connect layers." },
  ] as const;
</script>

<div class="selection-toolbar" role="group" aria-label="Segment selection tools">
  <div class="tool-row">
    {#each modes as mode (mode.id)}
      <button type="button" class="icon-button" {disabled} aria-label={mode.label} aria-pressed={tool.mode === mode.id || mode.id === "select" && tool.mode === "pan"} title={mode.tip} onclick={() => { onActivate(); tool.setMode(mode.id); }}><mode.icon size={16} aria-hidden="true" /></button>
    {/each}
      <select aria-label="Box coverage" title="By direction: drag right to select contained segments; drag left to select anything crossed." bind:value={tool.crossing} disabled={disabled}>
        <option value="direction">By direction</option>
        <option value={true}>Crossing</option><option value={false}>Contained</option>
      </select>
      <select aria-label="Box selection action" title="Replace the selection, add to it, or remove segments from it." bind:value={tool.boxAction} disabled={disabled}>
        <option value="replace">Replace</option><option value="add">Add</option><option value="remove">Remove</option>
      </select>
    <span class="text-slate-400" role="status">{tool.selected.length} selected</span>
    <button type="button" class="icon-button" aria-label="Clear" disabled={disabled || !tool.selected.length} onclick={tool.clear} title="Clear selected segments and the chain start."><X size={16} aria-hidden="true" /></button>
    <SelectionAssignmentMenu {tool} {geometry} {disabled} variant="button" triggerClass="flex h-8 w-8 items-center justify-center rounded border border-slate-700 hover:bg-slate-800 disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500" />
    {#if tool.canUndo}<button type="button" class="icon-button" aria-label="Undo assignment" title="Undo the last coil or layer assignment." {disabled} onclick={tool.undo}><Undo2 size={16} aria-hidden="true" /></button>{/if}
  </div>
  {#if tool.mode === "chain" || tool.selected.length}
    <div class="tool-row">
      <span class="text-slate-400" role="status">{tool.notice || (tool.mode === "chain" ? "Choose the first segment." : "Right-click to change coil or layer, or choose a destination in Layers.")}</span>
    </div>
  {/if}
</div>

<style>
  .selection-toolbar { display: flex; flex-direction: column; gap: .5rem; font-size: .75rem; }
  .tool-row { display: flex; align-items: center; flex-wrap: wrap; gap: .5rem; }
  button, select { border: 1px solid rgb(var(--slate-700)); border-radius: .25rem; background: rgb(var(--slate-900)); color: rgb(var(--slate-200)); padding: .25rem .5rem; }
  button[aria-pressed="true"] { border-color: #34d399; color: #6ee7b7; background: #064e3b; }
  .icon-button { display: inline-flex; align-items: center; justify-content: center; width: 2rem; height: 2rem; padding: 0; }
  button:disabled { opacity: .4; }
  :is(button, select):focus-visible { outline: 2px solid #34d399; outline-offset: 2px; }
</style>
