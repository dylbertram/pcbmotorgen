<script lang="ts">
  import type { CadGeometry } from "../../types";
  import type { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";
  import { cadCoilNames } from "../../cadPreview";
  let { tool, geometry, onActivate = () => {}, disabled = false }: { tool: CadSelectionTool; geometry: CadGeometry; onActivate?: () => void; disabled?: boolean } = $props();
  let coil = $state("");
  let layer = $state("");
  const uid = $props.id();
  const modes = [
    { id: "pan", label: "Pan", tip: "Drag to pan. Pinch or Ctrl-scroll to zoom." },
    { id: "select", label: "Select", tip: "Click a segment to select it. Shift-click adds or removes a segment." },
    { id: "chain", label: "Chain", tip: "Click the first and last segments to select the shortest connected chain. Vias connect segments across layers." },
    { id: "box", label: "Box", tip: "Drag a selection box. Choose crossing or contained, then replace, add, or remove." },
  ] as const;
</script>

<div class="selection-toolbar" role="group" aria-label="Segment selection tools">
  <div class="tool-row">
    {#each modes as mode (mode.id)}
      <button type="button" {disabled} aria-pressed={tool.mode === mode.id} title={mode.tip} onclick={() => { onActivate(); tool.setMode(mode.id); }}>{mode.label}</button>
    {/each}
    {#if tool.mode === "box"}
      <select aria-label="Box coverage" title="Crossing selects any touched segment. Contained selects only segments fully inside the box." bind:value={tool.crossing} disabled={disabled}>
        <option value={true}>Crossing</option><option value={false}>Contained</option>
      </select>
      <select aria-label="Box selection action" title="Replace the selection, add to it, or remove segments from it." bind:value={tool.boxAction} disabled={disabled}>
        <option value="replace">Replace</option><option value="add">Add</option><option value="remove">Remove</option>
      </select>
    {/if}
    <span class="text-slate-400" role="status">{tool.selected.length} selected</span>
    <button type="button" disabled={disabled || !tool.selected.length} onclick={tool.clear} title="Clear selected segments and the chain start.">Clear</button>
  </div>
  {#if tool.mode !== "pan" || tool.selected.length}
    <div class="tool-row">
      <label>Coil <input aria-label="Assign selected segments to coil" list={`${uid}-coils`} placeholder="Keep coil" bind:value={coil} {disabled} title="Enter a coil name or choose an existing coil." /></label>
      <datalist id={`${uid}-coils`}>{#each cadCoilNames(geometry) as name (name)}<option value={name}></option>{/each}</datalist>
      <label>Layer <select aria-label="Assign selected segments to layer" bind:value={layer} {disabled}><option value="">Keep layer</option>{#each geometry.layer_z_mm as _, i (i)}<option value={String(i)}>L{i}</option>{/each}</select></label>
      <button type="button" disabled={disabled || !tool.selected.length || (!coil.trim() && layer === "")} onclick={() => tool.apply(coil, layer)} title="Move selected segments to this coil or layer. Vias stay unchanged; affected coil terminals are cleared.">Assign</button>
      {#if tool.canUndo}<button type="button" {disabled} onclick={tool.undo}>Undo assignment</button>{/if}
      <span class="text-slate-400" role="status">{tool.notice || (tool.mode === "chain" ? "Choose the first segment." : "Shift-click to add or remove.")}</span>
    </div>
  {/if}
</div>

<style>
  .selection-toolbar { display: flex; flex-direction: column; gap: .5rem; font-size: .75rem; }
  .tool-row { display: flex; align-items: center; flex-wrap: wrap; gap: .5rem; }
  button, select, input { border: 1px solid rgb(var(--slate-700)); border-radius: .25rem; background: rgb(var(--slate-900)); color: rgb(var(--slate-200)); padding: .25rem .5rem; }
  button[aria-pressed="true"] { border-color: #34d399; color: #6ee7b7; background: #064e3b; }
  button:disabled { opacity: .4; }
  label { display: flex; gap: .35rem; align-items: center; color: rgb(var(--slate-300)); }
  input { width: 7rem; }
  :is(button, select, input):focus-visible { outline: 2px solid #34d399; outline-offset: 2px; }
</style>
