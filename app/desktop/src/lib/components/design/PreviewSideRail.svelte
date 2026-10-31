<script lang="ts">
  /**
   * Motor settings, coil ends and driver controls use the left rail; Layers
   * stays on the right. CAD import retains its single right rail.
   *
    * Each toggle pulls a panel out from the rail: the
     * Layers panel (phases containing layers or layers containing phases),
     * with global visibility options in View. Import previews keep local options,
     * terminals,
    * and optional driver settings in the expanded coil preview.
   * Panels overlay the drawing, so opening one never resizes the viewer, and
    * only one is open at a time. Terminal picking keeps the panel open for
    * clicks in the drawing; Escape or its close button cancels the draft.
    * Outside clicks dismiss by default (the CAD import viewer) but the coil
    * preview passes `dismissOnOutsideClick={false}` (kata qfdz).
   */
  import { fly } from "svelte/transition";
  import { onDestroy } from "svelte";
  import { Layers, X, Plug, CircuitBoard, Route, Magnet, Gauge } from "@lucide/svelte";
  import type { Snippet } from "svelte";
  import { DESIGN_PANELS, isDesignPanel, isLeftPanel, type DesignPanelId, type PreviewPanelId } from "./previewPanels";
  import CoilTerminalPanel from "./CoilTerminalPanel.svelte";
  import type { CoilTerminalTool } from "../../utils/coilTerminalTool.svelte";
  import CoilPreviewVisibilityPanel from "./CoilPreviewVisibilityPanel.svelte";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import type { CadGeometry, DriveAnalysis } from "../../types";
  import DriverSelector from "../simulate/DriverSelector.svelte";
  import { formatSi } from "../../format";
  import HelpTag from "../ui/HelpTag.svelte";
  import seriesInductorSvg from "../../assets/series-inductor.svg";
  import type { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";
  import type { ConfigStore } from "../../stores/config.svelte";
  import NumberField from "../ui/NumberField.svelte";

  let { view, layers, coils = [], isCoilVisible, onToggleCoil, label,
    phases = [], showMotorControls = false, hasPolePitchData = false,
    hasBandWidthData = false, hasPoleRegionData = false, poleRegionPhases = [],
    geometry, selection, assignmentDisabled = false, terminalTool, onStartTerminals,
    terminalsDisabled = false, dismissOnOutsideClick = true, viewControlsInMenu = false, config, generated = false,
    drive = null, driveError = null, drivePending = false,
    designSettings, designOnly = false, drawingOnly = false, open = $bindable<PreviewPanelId | null>(null), active = true }: {
    designOnly?: boolean;
    drawingOnly?: boolean;
    active?: boolean;
    designSettings?: Snippet<[DesignPanelId]>;
    open?: PreviewPanelId | null;
    /** Shared motor settings, supplied by the expanded coil preview. */
    config?: ConfigStore;
    generated?: boolean;
    drive?: DriveAnalysis | null;
    driveError?: string | null;
    drivePending?: boolean;
    view: CoilPreviewViewState;
    layers: { idx: number }[];
    coils?: { name: string; colorIdx: number }[];
    isCoilVisible?: (name: string) => boolean;
    onToggleCoil?: (name: string) => void;
    /** Accessible name of the Layers panel. */
    label: string;
    phases?: { idx: number; name: string; colorIdx: number }[];
    showMotorControls?: boolean;
    /** Global display options live in the motor document's native View menu. */
    viewControlsInMenu?: boolean;
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
  } = $props();

  const rippleCheck = $derived(drive?.checks.find((check) => check.id === "ripple"));
  let railEl: HTMLDivElement | null = $state(null);
  const triggers = $state<Partial<Record<PreviewPanelId, HTMLButtonElement | null>>>({});
  const panelClass = $derived(`absolute bottom-0 top-0 z-30 flex w-60 flex-col overflow-hidden border-slate-700 bg-slate-900 text-slate-200 ${designOnly ? 'left-full max-w-[calc(100vw-8.25rem)] border-r shadow-[12px_0_20px_-8px_rgba(0,0,0,0.4)] [clip-path:inset(0_-32px_0_0)]' : 'right-full max-w-[calc(100vw-6rem)] border-l shadow-xl shadow-black/40'}`);
  const designIcons = { stackup: Layers, routing: Route, magnets: Magnet, drive: Gauge };
  const activeDesignPanel = $derived(DESIGN_PANELS.find(({ id }) => id === open));
  onDestroy(() => { if (!drawingOnly) { terminalTool?.cancel(); view.setTerminalPanelOpen(false); } });
  // An outside request (the Simulation tab's ends alert) sets
  // `view.terminalPanelOpen`; mirror it into the local panel state.
  $effect(() => {
    if (!drawingOnly && view.terminalPanelOpen && open !== "terminals") open = "terminals";
  });

  function toggle(panel: PreviewPanelId) {
    if (open === "terminals") terminalTool?.cancel();
    open = open === panel ? null : panel;
    view.setTerminalPanelOpen(open === "terminals");
  }
  function close() {
    const panel = open;
    open = null;
    view.setTerminalPanelOpen(false);
    if (panel === "terminals") terminalTool?.cancel();
    if (panel) triggers[panel]?.focus();
  }
  function handleKeydown(event: KeyboardEvent) {
    if (!active || !open || event.key !== "Escape") return;
    if (designOnly ? !isLeftPanel(open) : drawingOnly ? isLeftPanel(open) : isDesignPanel(open)) return;
    const target = event.target as Element | null;
    const modal = target?.closest('[aria-modal="true"]');
    // Portaled dialogs and menus own Escape before the underlying drawer.
    if (modal && !modal.contains(railEl)) return;
    if (target?.closest('[role="menu"], [role="listbox"]') && !railEl?.contains(target)) return;
    event.preventDefault();
    event.stopPropagation();
    close();
  }
  function handlePointerDown(event: PointerEvent) {
    if (!active || !open || open === "terminals" || !dismissOnOutsideClick) return;
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
  <div role="toolbar" aria-label={designOnly ? "Design side tools" : "Preview side tools"} aria-orientation="vertical" class="flex h-full w-full flex-col items-center gap-2 overflow-y-auto {designOnly ? 'border-r' : 'border-l'} border-slate-700 bg-slate-900 py-2">
    {#if designSettings}
      {#each DESIGN_PANELS as panel (panel.id)}
      {@const Icon = designIcons[panel.id]}
      <button type="button" bind:this={triggers[panel.id]} aria-label={panel.label} aria-expanded={open === panel.id} onclick={() => toggle(panel.id)}
        class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-transparent text-slate-300 hover:bg-slate-800 aria-expanded:border-emerald-500 aria-expanded:text-emerald-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
        title={panel.label}>
        <Icon size={16} aria-hidden="true" />
      </button>
      {/each}
    {/if}
    {#if !designOnly}<button type="button" bind:this={triggers.layers} aria-label="Layers" aria-expanded={open === "layers"} onclick={() => toggle("layers")}
      class="flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-slate-300 hover:bg-slate-800 aria-expanded:border-emerald-500 aria-expanded:text-emerald-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
      title="Show visibility by phase or layer.">
      <Layers size={16} aria-hidden="true" />
    </button>
    {/if}
    {#if !drawingOnly}
    {#if geometry && terminalTool && onStartTerminals}
      <button type="button" bind:this={triggers.terminals} aria-label="Set coil terminals" aria-expanded={open === "terminals"} disabled={terminalsDisabled} onclick={() => toggle("terminals")}
        class="flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-slate-300 hover:bg-slate-800 aria-expanded:border-emerald-500 aria-expanded:text-emerald-300 disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-emerald-500" title="Select the driver end of each coil.">
        <Plug size={16} aria-hidden="true" />
      </button>
    {/if}
    {#if config}
      <button type="button" bind:this={triggers.driver} aria-label="Driver settings" aria-expanded={open === "driver"} onclick={() => toggle("driver")}
        class="flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-slate-300 hover:bg-slate-800 aria-expanded:border-emerald-500 aria-expanded:text-emerald-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
        title="Choose a driver and set external series inductance.">
        <CircuitBoard size={16} aria-hidden="true" />
      </button>
    {/if}
    {/if}
  </div>

  {#if activeDesignPanel && designSettings}
    <div role="dialog" aria-label={activeDesignPanel.label} aria-modal="false" class="absolute bottom-14 lg:bottom-0 left-full top-0 z-30 flex w-[400px] max-w-[calc(100vw-8.25rem)] flex-col overflow-hidden border-r border-slate-700 bg-slate-900 text-slate-200 shadow-[12px_0_20px_-8px_rgba(0,0,0,0.4)] [clip-path:inset(0_-32px_0_0)]" transition:fly={{ x: -16, duration: 140 }}>
      <header class="flex shrink-0 items-center justify-between border-b border-slate-700 px-3 py-2">
        <div class="flex items-center"><h3 class="text-sm font-semibold">{activeDesignPanel.label}</h3>{#if activeDesignPanel.id === "stackup"}<HelpTag label="About the backplane model" tip="Fundamental-field model with saturation and eddy currents. Infinite layers; ignores edges, hysteresis and core losses." />{/if}</div>
        <button type="button" aria-label={`Close ${activeDesignPanel.label.toLowerCase()} panel`} onclick={close} class="rounded p-1 text-slate-400 hover:bg-slate-800"><X size={16} aria-hidden="true" /></button>
      </header>
      <div class="min-h-0 flex-1">{#key activeDesignPanel.id}{@render designSettings(activeDesignPanel.id)}{/key}</div>
    </div>
  {/if}

  {#if !drawingOnly}
  {#if open === "terminals" && geometry && terminalTool && onStartTerminals}
    <div role="dialog" aria-label="Coil terminals" aria-modal="false" class={`${panelClass} ${showMotorControls ? 'max-lg:bottom-44' : ''}`} transition:fly={{ x: designOnly ? -16 : 16, duration: 140 }}>
      <header class="flex shrink-0 items-center justify-between border-b border-slate-700 px-3 py-2">
        <h3 class="text-sm font-semibold">Coil ends</h3>
        <button type="button" aria-label="Close terminals panel" onclick={close} class="rounded p-1 text-slate-400 hover:bg-slate-800"><X size={16} aria-hidden="true" /></button>
      </header>
      <div class="min-h-0 overflow-y-auto overscroll-contain p-3">
        <CoilTerminalPanel tool={terminalTool} {geometry} declaredConnection={generated ? config?.generatorConnection : null} connectionLocked={generated && !!config?.generatorEndType}
          connectionParam={generated && !config?.generatorEndType ? config?.routing_param_defs.find((def) => def.key === "connection") : undefined}
          connectionValue={config?.routing_params.connection} onConnectionParamChange={generated && config ? (value) => config?.setRoutingParam("connection", value) : undefined}
          onStart={(coil) => { selection?.setMode("pan"); onStartTerminals(coil); }} disabled={terminalsDisabled} />
      </div>
    </div>
  {/if}

  {#if open === "driver" && config}
    <div role="dialog" aria-label="Preview driver settings" aria-modal="false" class={`${panelClass} ${showMotorControls ? 'max-lg:bottom-14' : ''}`} transition:fly={{ x: designOnly ? -16 : 16, duration: 140 }}>
      <header class="flex shrink-0 items-center justify-between border-b border-slate-700 px-3 py-2">
        <h3 class="text-sm font-semibold">Driver</h3>
        <button type="button" aria-label="Close driver panel" onclick={close} class="rounded p-1 text-slate-400 hover:bg-slate-800"><X size={16} aria-hidden="true" /></button>
      </header>
      <div class="min-h-0 overflow-y-auto overscroll-contain p-3">
        <fieldset class="space-y-2">
          <legend class="text-xs font-semibold text-slate-200">Driver inductor</legend>
          <label class="flex items-center justify-between gap-2 text-xs text-slate-300">
            <span>Per phase (µH)<HelpTag label="About series inductance" tip="One external inductor per driver output. Applies to every phase; 0 means none. Not part of PCB geometry." equation={String.raw`V_L = L\frac{\mathrm{d}i}{\mathrm{d}t}`} image={seriesInductorSvg} imageAlt="Each driver output connects through an added inductor to a PCB winding." /></span>
            <NumberField value={config.drive.series_inductance_h * 1e6} min={0} step={1}
              ariaLabel="Series inductor per phase (µH)" class="w-20 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
              onCommit={(v) => { if (config) config.drive = { ...config.drive, series_inductance_h: v * 1e-6 }; }} />
          </label>
          <p class="text-[11px] text-slate-400">Adding inductance can reduce PWM current ripple, but needs more voltage at speed.</p>
        </fieldset>
        <div class="mt-4 border-t border-slate-700 pt-3"><DriverSelector {config} /></div>
        <section aria-label="Preview driver simulation results" aria-busy={drivePending} class="mt-4 space-y-2 border-t border-slate-700 pt-3">
          <h4 class="text-xs font-semibold text-slate-200">Simulation results</h4>
          {#if drivePending}
            <p role="status" class="text-[11px] text-slate-400">Updating driver simulation…</p>
          {:else if driveError}
            <p role="alert" class="text-[11px] text-rose-300">{driveError}</p>
          {:else if drive}
            <p class="text-[11px] text-slate-400">{drive.driver_name} · {formatSi(drive.pwm_hz, "Hz")} PWM</p>
            <dl class="space-y-2 text-xs">
              <div class="flex flex-wrap justify-between gap-1"><dt class="text-slate-400">Current ripple<HelpTag label="About current ripple" tip="Peak-to-peak current variation caused by PWM switching." equation={String.raw`\Delta I_{\mathrm{pp}} = I_{\max} - I_{\min}`} /></dt><dd class="font-mono text-slate-100">{formatSi(drive.ripple_pp_a, "A")}</dd></div>
              <div class="flex flex-wrap justify-between gap-1"><dt class="text-slate-400">Effective phase inductance<HelpTag label="About effective inductance" tip="Winding inductance plus the external series inductor." equation={String.raw`L_{\mathrm{eff}} = L_{\mathrm{winding}} + L_{\mathrm{series}}`} /></dt><dd class="font-mono text-slate-100">{formatSi(drive.effective_inductance_h, "H")}</dd></div>
              <div class="flex flex-wrap justify-between gap-1"><dt class="text-slate-400">Additional L needed<HelpTag label="About additional inductance" tip="Extra inductance still needed per phase to meet the ripple limit at this PWM frequency." /></dt><dd class="font-mono text-slate-100">{formatSi(drive.added_inductance_h, "H")}</dd></div>
              <div class="flex flex-wrap justify-between gap-1"><dt class="text-slate-400">Minimum PWM<HelpTag label="About minimum PWM" tip="Switching frequency needed to meet the ripple limit with this total inductance." /></dt><dd class="font-mono text-slate-100">{formatSi(drive.min_pwm_hz, "Hz")}</dd></div>
            </dl>
            {#if rippleCheck}
              <p class="text-xs {rippleCheck.status === 'pass' ? 'text-emerald-300' : rippleCheck.status === 'unknown' ? 'text-slate-400' : 'text-amber-300'}">Ripple check: {rippleCheck.status}<HelpTag label="Ripple check details" tip={rippleCheck.detail} /></p>
            {/if}
            <p class="text-[11px] text-slate-500">Full checks in Simulate.</p>
          {:else}
            <p role="status" class="text-[11px] text-slate-400">Driver results unavailable. Check the design and coil connections in Simulate.</p>
          {/if}
        </section>
      </div>
    </div>
  {/if}

  {/if}
  {#if !designOnly}
  {#if open === "layers"}
    <div role="dialog" aria-label={label} aria-modal="false" class={`${panelClass} ${showMotorControls ? 'max-lg:bottom-14' : ''}`} transition:fly={{ x: 16, duration: 140 }}>
      <header class="flex shrink-0 items-center justify-between border-b border-slate-700 px-3 py-2">
        <h3 class="text-sm font-semibold">Layers</h3>
        <button type="button" aria-label="Close layers panel" onclick={close} class="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500">
          <X size={16} aria-hidden="true" />
        </button>
      </header>
      <div class="min-h-0 overflow-y-auto overscroll-contain p-3">
        <CoilPreviewVisibilityPanel {view} uniqueLayers={layers} uniquePhases={phases} {coils} {isCoilVisible} {onToggleCoil}
          {showMotorControls} {viewControlsInMenu} {hasPolePitchData} {hasBandWidthData} {hasPoleRegionData} {poleRegionPhases} {geometry} {selection} {assignmentDisabled} />
      </div>
    </div>
  {/if}

  {/if}
</div>
