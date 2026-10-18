<script lang="ts">
  /**
   * Shared right-side dock for the coiled preview and CAD import viewers.
   *
    * Each toggle pulls a panel out from the rail: the
   * Layers panel (coil/phase/layer tree plus diagnostics overlays) and the
    * Display panel (traces, copper layers, vias and arrows), terminals,
    * and optional driver settings in the expanded coil preview.
   * Panels overlay the drawing, so opening one never resizes the viewer, and
    * only one is open at a time. Terminal picking keeps the panel open for
    * clicks in the drawing; Escape or its close button cancels the draft.
    * Outside clicks dismiss by default (the CAD import viewer) but the coil
    * preview passes `dismissOnOutsideClick={false}` (kata qfdz).
   */
  import { fly } from "svelte/transition";
  import { onDestroy } from "svelte";
  import { Layers, SlidersHorizontal, X, Plug, CircuitBoard } from "@lucide/svelte";
  import CoilTerminalPanel from "./CoilTerminalPanel.svelte";
  import type { CoilTerminalTool } from "../../utils/coilTerminalTool.svelte";
  import CoilPreviewVisibilityPanel from "./CoilPreviewVisibilityPanel.svelte";
  import CoilPreviewDisplayPanel from "./CoilPreviewDisplayPanel.svelte";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import type { CadGeometry } from "../../types";
  import type { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";
  import type { ConfigStore } from "../../stores/config.svelte";
  import NumberField from "../ui/NumberField.svelte";

  let { view, layers, coils = [], isCoilVisible, onToggleCoil, label, displayLabel,
    phases = [], showMotorControls = false, hasPolePitchData = false,
    hasBandWidthData = false, hasPoleRegionData = false, poleRegionPhases = [],
    geometry, selection, assignmentDisabled = false, terminalTool, onStartTerminals,
    terminalsDisabled = false, dismissOnOutsideClick = true, showViewMode = false, config }: {
    /** Shared motor settings, supplied by the expanded coil preview. */
    config?: ConfigStore;
    view: CoilPreviewViewState;
    layers: { idx: number }[];
    coils?: { name: string; colorIdx: number }[];
    isCoilVisible?: (name: string) => boolean;
    onToggleCoil?: (name: string) => void;
    /** Accessible name of the Layers panel. */
    label: string;
    /** Accessible name of the Display panel. */
    displayLabel: string;
    phases?: { idx: number; name: string; colorIdx: number }[];
    showMotorControls?: boolean;
    hasPolePitchData?: boolean;
    hasBandWidthData?: boolean;
    hasPoleRegionData?: boolean;
    poleRegionPhases?: string[];
    geometry?: CadGeometry | null;
    selection?: CadSelectionTool;
    assignmentDisabled?: boolean;
    terminalTool?: CoilTerminalTool;
    onStartTerminals?: (coil?: string) => void;
    terminalsDisabled?: boolean;
    /**
     * Close the open panel when a pointer lands outside the rail. The CAD
     * import viewer dismisses this way; the coil preview keeps its panel open
     * so an outside click never surprises the user (kata qfdz).
     */
    dismissOnOutsideClick?: boolean;
    /** Offer the Top-down / 3D switch in the Display panel (coil preview). */
    showViewMode?: boolean;
  } = $props();

  type PanelId = "layers" | "display" | "terminals" | "driver";
  let open = $state<PanelId | null>(null);
  let railEl: HTMLDivElement | null = $state(null);
  const triggers: Record<PanelId, HTMLButtonElement | null> = { layers: null, display: null, terminals: null, driver: null };
  const panelClass = "absolute bottom-0 right-full top-0 z-30 flex w-60 max-w-[calc(100vw-4rem)] flex-col overflow-hidden border-l border-slate-700 bg-slate-900 text-slate-200 shadow-xl shadow-black/40";
  onDestroy(() => { terminalTool?.cancel(); view.terminalPanelOpen = false; });
  // An outside request (the Simulation tab's ends alert) sets
  // `view.terminalPanelOpen`; mirror it into the local panel state.
  $effect(() => {
    if (view.terminalPanelOpen && open !== "terminals") open = "terminals";
  });

  function toggle(panel: PanelId) {
    if (open === "terminals") terminalTool?.cancel();
    open = open === panel ? null : panel;
    view.terminalPanelOpen = open === "terminals";
  }
  function close() {
    const panel = open;
    open = null;
    view.terminalPanelOpen = false;
    if (panel === "terminals") terminalTool?.cancel();
    if (panel) triggers[panel]?.focus();
  }
  function handleKeydown(event: KeyboardEvent) {
    if (!open || event.key !== "Escape") return;
    event.preventDefault();
    event.stopPropagation();
    close();
  }
  function handlePointerDown(event: PointerEvent) {
    if (!open || open === "terminals" || !dismissOnOutsideClick) return;
    // Menus and popovers opened from the panel are portaled to the body, so they
    // are outside the rail. bits-ui tags those floating layers, and clicks in
    // them must not dismiss the panel.
    const path = event.composedPath();
    if (path.some((node) => node instanceof HTMLElement && node.hasAttribute("data-bits-floating-content-wrapper"))) return;
    if (!railEl?.contains(event.target as Node)) open = null;
  }
</script>

<svelte:window onkeydowncapture={handleKeydown} />
<svelte:document onpointerdown={handlePointerDown} />

<div bind:this={railEl} class="relative h-full w-11">
  <div role="toolbar" aria-label="Preview side tools" aria-orientation="vertical" class="flex h-full w-full flex-col items-center gap-2 border-l border-slate-700 bg-slate-900 py-2">
    <button type="button" bind:this={triggers.layers} aria-label="Layers" aria-expanded={open === "layers"} onclick={() => toggle("layers")}
      class="flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-slate-300 hover:bg-slate-800 aria-expanded:border-emerald-500 aria-expanded:text-emerald-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
      title="Show the coil, phase and layer tree.">
      <Layers size={16} aria-hidden="true" />
    </button>
    <button type="button" bind:this={triggers.display} aria-label="Display" aria-expanded={open === "display"} onclick={() => toggle("display")}
      class="flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-slate-300 hover:bg-slate-800 aria-expanded:border-emerald-500 aria-expanded:text-emerald-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
      title="Show display options: traces, copper layers and vias.">
      <SlidersHorizontal size={16} aria-hidden="true" />
    </button>
    {#if geometry && terminalTool && onStartTerminals}
      <button type="button" bind:this={triggers.terminals} aria-label="Set coil terminals" aria-expanded={open === "terminals"} disabled={terminalsDisabled} onclick={() => toggle("terminals")}
        class="flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-slate-300 hover:bg-slate-800 aria-expanded:border-emerald-500 aria-expanded:text-emerald-300 disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-emerald-500" title="Select the driver end of each coil.">
        <Plug size={16} aria-hidden="true" />
      </button>
    {/if}
    {#if config}
      <button type="button" bind:this={triggers.driver} aria-label="Driver settings" aria-expanded={open === "driver"} onclick={() => toggle("driver")}
        class="flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-slate-300 hover:bg-slate-800 aria-expanded:border-emerald-500 aria-expanded:text-emerald-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
        title="Set external series inductance at the driver ends.">
        <CircuitBoard size={16} aria-hidden="true" />
      </button>
    {/if}
  </div>

  {#if open === "terminals" && geometry && terminalTool && onStartTerminals}
    <div role="dialog" aria-label="Coil terminals" aria-modal="false" class={`${panelClass} ${showMotorControls ? 'max-sm:bottom-20' : ''}`} transition:fly={{ x: 16, duration: 140 }}>
      <header class="flex shrink-0 items-center justify-between border-b border-slate-700 px-3 py-2">
        <h3 class="text-sm font-semibold">Coil ends</h3>
        <button type="button" aria-label="Close terminals panel" onclick={close} class="rounded p-1 text-slate-400 hover:bg-slate-800"><X size={16} aria-hidden="true" /></button>
      </header>
      <div class="min-h-0 overflow-y-auto overscroll-contain p-3">
        <CoilTerminalPanel tool={terminalTool} {geometry} onStart={(coil) => { selection?.setMode("pan"); onStartTerminals(coil); }} disabled={terminalsDisabled} />
      </div>
    </div>
  {/if}

  {#if open === "driver" && config}
    <div role="dialog" aria-label="Preview driver settings" aria-modal="false" class={panelClass} transition:fly={{ x: 16, duration: 140 }}>
      <header class="flex shrink-0 items-center justify-between border-b border-slate-700 px-3 py-2">
        <h3 class="text-sm font-semibold">Driver</h3>
        <button type="button" aria-label="Close driver panel" onclick={close} class="rounded p-1 text-slate-400 hover:bg-slate-800"><X size={16} aria-hidden="true" /></button>
      </header>
      <div class="min-h-0 overflow-y-auto overscroll-contain p-3">
        <fieldset class="space-y-2">
          <legend class="text-xs font-semibold text-slate-200">Driver inductor</legend>
          <label class="flex items-center justify-between gap-2 text-xs text-slate-300">
            Per phase (µH)
            <NumberField value={config.drive.series_inductance_h * 1e6} min={0} step={1}
              ariaLabel="Series inductor per phase (µH)" class="w-20 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
              onCommit={(v) => { if (config) config.drive = { ...config.drive, series_inductance_h: v * 1e-6 }; }} />
          </label>
          <p class="text-[11px] text-slate-400">An external series inductor at each driver end. The same value applies to every phase. Use 0 for none. Included in driver simulation, not PCB geometry.</p>
        </fieldset>
      </div>
    </div>
  {/if}

  {#if open === "layers"}
    <div role="dialog" aria-label={label} aria-modal="false" class={panelClass} transition:fly={{ x: 16, duration: 140 }}>
      <header class="flex shrink-0 items-center justify-between border-b border-slate-700 px-3 py-2">
        <h3 class="text-sm font-semibold">Layers</h3>
        <button type="button" aria-label="Close layers panel" onclick={close} class="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500">
          <X size={16} aria-hidden="true" />
        </button>
      </header>
      <div class="min-h-0 overflow-y-auto overscroll-contain p-3">
        <CoilPreviewVisibilityPanel {view} uniqueLayers={layers} uniquePhases={phases} {coils} {isCoilVisible} {onToggleCoil}
          {showMotorControls} {hasPolePitchData} {hasBandWidthData} {hasPoleRegionData} {poleRegionPhases} {geometry} {selection} {assignmentDisabled} />
      </div>
    </div>
  {/if}

  {#if open === "display"}
    <div role="dialog" aria-label={displayLabel} aria-modal="false" class={panelClass} transition:fly={{ x: 16, duration: 140 }}>
      <header class="flex shrink-0 items-center justify-between border-b border-slate-700 px-3 py-2">
        <h3 class="text-sm font-semibold">Display</h3>
        <button type="button" aria-label="Close display panel" onclick={close} class="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500">
          <X size={16} aria-hidden="true" />
        </button>
      </header>
      <div class="min-h-0 overflow-y-auto overscroll-contain p-3">
        <CoilPreviewDisplayPanel {view} uniqueLayers={layers} {showViewMode} />
      </div>
    </div>
  {/if}
</div>
