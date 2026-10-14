<script lang="ts">
  import { GitMerge, Undo2, Plug } from "@lucide/svelte";
  import type { CadGeometry } from "../../types";
  import type { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";
  import type { CoilTerminalTool } from "../../utils/coilTerminalTool.svelte";
  import type { CoilPreviewMeasure } from "../../utils/coilPreviewMeasure.svelte";
  import CadSelectionToolbar from "./CadSelectionToolbar.svelte";
  import CoilPreviewMeasureToolbar from "./CoilPreviewMeasureToolbar.svelte";

  let { label, geometry, selection, measure, terminalTool, disabled = false,
    onActivateSelection, onStartTerminals, onSimplify, onUndoSimplify,
    simplifyNotice = "", onPrepareGeometry, borderless = false }: {
    label: string;
    geometry: CadGeometry | null;
    selection: CadSelectionTool;
    measure: CoilPreviewMeasure;
    terminalTool?: CoilTerminalTool;
    disabled?: boolean;
    onActivateSelection?: () => void;
    onStartTerminals?: (coil?: string) => void;
    onSimplify?: () => void;
    onUndoSimplify?: () => void;
    simplifyNotice?: string;
    onPrepareGeometry?: () => Promise<boolean>;
    borderless?: boolean;
  } = $props();
  let preparing = $state(false);
  let error = $state("");
  // One fixed-height status line under the toolbar divider. Reserving the row
  // keeps the drawing from shifting when the selection or merge hint appears.
  let status = $derived(
    error
      || (selection.mode === "chain" || selection.selected.length
        ? selection.notice || (selection.mode === "chain" ? "Choose the first segment." : "Right-click to change coil or layer, or choose a destination in Layers.")
        : "")
      || simplifyNotice
      || terminalTool?.notice
      || "",
  );
  function activateSelection() {
    terminalTool?.cancel();
    measure.mode = false;
    onActivateSelection?.();
  }
  async function prepare() {
    preparing = true;
    error = "";
    try {
      if (await onPrepareGeometry?.()) { activateSelection(); selection.setMode("select"); }
    } catch (e) { error = e instanceof Error ? e.message : String(e); }
    finally { preparing = false; }
  }
</script>

<div role="toolbar" aria-label={label} class="flex shrink-0 flex-col">
  <!-- The bottom rule stays after the editing boxes were removed; it is the
       line between the toolbar and the viewer. -->
  <div class="flex flex-wrap items-start gap-2 border-b border-slate-700 {borderless ? '' : 'border-t py-2'}">
  {#if geometry}
    <CadSelectionToolbar tool={selection} {geometry} {disabled} onActivate={activateSelection} />
  {:else if onPrepareGeometry}
    <button type="button" onclick={prepare} disabled={disabled || preparing} class="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-300 disabled:opacity-40" title="Create editable geometry to select and reassign segments. Edits stop following the routing settings.">{preparing ? "Preparing segments…" : "Edit segments"}</button>
  {/if}
  <CoilPreviewMeasureToolbar {measure} {disabled} onToggle={() => { selection.setMode("pan"); terminalTool?.cancel(); measure.toggleMode(); }} />
  {#if onSimplify}
    <button type="button" aria-label="Simplify lines" onclick={() => { selection.clear(); selection.setMode("pan"); onSimplify?.(); }} disabled={disabled || terminalTool?.active} class="icon-tool" title="Simplify lines: merge collinear lines in saved and exported geometry."><GitMerge size={16} aria-hidden="true" /></button>
    {#if onUndoSimplify}<button type="button" aria-label="Undo simplify" onclick={() => { selection.clear(); onUndoSimplify?.(); }} disabled={disabled || terminalTool?.active} class="icon-tool" title="Undo line simplification."><Undo2 size={16} aria-hidden="true" /></button>{/if}
  {/if}
  {#if terminalTool && onStartTerminals}
    <button type="button" aria-label="Set coil terminals" onclick={() => { selection.setMode("pan"); onStartTerminals?.(); }} {disabled} aria-pressed={terminalTool.active} class="icon-tool" title="Set coil terminals: review open ends, change either endpoint, or flip IN and OUT."><Plug size={16} aria-hidden="true" /></button>
  {/if}
  </div>
  <div class="flex h-5 min-w-0 items-center text-xs text-slate-400">
    <span role="status" class="truncate" title={status}>{status}</span>
  </div>
</div>

<style>
  .icon-tool { display: inline-flex; align-items: center; justify-content: center; width: 2rem; height: 2rem; flex-shrink: 0; border: 1px solid rgb(var(--slate-700)); border-radius: .25rem; background: rgb(var(--slate-800)); color: rgb(var(--slate-300)); }
  .icon-tool:hover { color: #6ee7b7; }
  .icon-tool[aria-pressed="true"] { border-color: #34d399; color: #6ee7b7; background: #064e3b; }
  .icon-tool:disabled { opacity: .4; }
  button:focus-visible { outline: 2px solid #34d399; outline-offset: 2px; }
</style>
