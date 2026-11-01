<script lang="ts">
  import { Tabs } from "bits-ui";
  import type { PowerRequirementsInput } from "../../powerRequirements";
  import { tick } from "svelte";
  import { ChevronDown, ChevronUp, FlaskConical } from "@lucide/svelte";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { ForceSweepResult, FrictionBudgetDto, HeightStackResultDto, DriveAnalysis, CadGeometry } from "../../types";
  import { cadMappingProblems } from "../../cadMapping";
  import { inferMissingCoilEnds } from "../../cadTerminals";
  import { usesDeltaConnection } from "../../driverConnection";
  import MovePowerPanel from "../simulate/MovePowerPanel.svelte";
  import ForcePanel from "../simulate/ForcePanel.svelte";
  import FieldsPanel from "../simulate/FieldsPanel.svelte";
  import DcCouplingPanel from "../simulate/DcCouplingPanel.svelte";

  let { config, active, open, availableHeight, sweep, friction, height, drive,
    driveError = null, error, cadGeometry = null, onConfigureWinding,
    onSelectEnds, onUseInferredEnds, powerInput, autoSimulation = $bindable(true), loading = false, onRun, canRun = true,
    onOpenFieldSettings, designName = "Untitled design" }: {
    autoSimulation?: boolean;
    loading?: boolean;
    onRun?: () => void;
    canRun?: boolean;
    config: ConfigStore;
    active: boolean;
    open: boolean;
    availableHeight: number;
    sweep: ForceSweepResult | null;
    friction: FrictionBudgetDto | null;
    height: HeightStackResultDto | null;
    drive: DriveAnalysis | null;
    driveError?: string | null;
    error: string | null;
    cadGeometry?: CadGeometry | null;
    onConfigureWinding?: () => void;
    onSelectEnds?: () => void;
    onUseInferredEnds?: () => void;
    powerInput: PowerRequirementsInput;
    onOpenFieldSettings?: () => void;
    designName?: string;
  } = $props();

  const results = [
    { id: "move", label: "Move & power" },
    { id: "force", label: "Force" },
    { id: "fields", label: "Fields" },
  ];
  let selected = $state("move");
  let requestedHeight = $state(320);
  let collapsed = $state(false);
  const minHeight = $derived(Math.min(160, Math.max(80, availableHeight * 0.4)));
  const maxHeight = $derived(Math.max(minHeight, availableHeight - 160));
  const panelHeight = $derived(Math.round(Math.min(maxHeight, Math.max(minHeight, requestedHeight))));
  const dockId = $props.id();
  let drag: { pointer: number; y: number; height: number } | null = null;
  const coilEnds = $derived(cadGeometry ? inferMissingCoilEnds(cadGeometry) : null);
  let dock = $state<HTMLElement | null>(null);
  const scrollOffsets: Record<string, number> = {};
  let restoringScroll = false;
  function rememberScroll(event: Event) {
    const panel = event.target;
    if (!open || collapsed || restoringScroll || !(panel instanceof HTMLElement) || !panel.clientHeight) return;
    const key = panel.dataset.dockPanel;
    const maximum = panel.scrollHeight - panel.clientHeight;
    // Pending results can temporarily remove the scrollable content. That
    // browser-generated clamp is not a request to forget the user's position.
    if (!key || maximum <= 0 || (maximum < (scrollOffsets[key] ?? 0) && panel.scrollTop >= maximum)) return;
    scrollOffsets[key] = panel.scrollTop;
  }
  $effect(() => {
    const node = dock, visible = open && !collapsed, tab = selected;
    if (!node || !visible) return;
    let cancelled = false;
    let cleanup = () => {};
    restoringScroll = true;
    void tick().then(() => {
      if (cancelled) return;
      const panel = node.querySelector<HTMLElement>(`[data-dock-panel="${tab}"]`);
      restoringScroll = false;
      if (!panel) return;
      const restore = () => {
        // Do not overwrite a fresh user scroll before its queued scroll event
        // has updated the memory. Restore only a lost positive offset at zero.
        if (cancelled || !(scrollOffsets[tab] > 0) || panel.scrollTop !== 0) return;
        restoringScroll = true;
        panel.scrollTop = scrollOffsets[tab];
        restoringScroll = false;
      };
      const observer = new ResizeObserver(restore);
      const observeChildren = () => {
        observer.disconnect();
        observer.observe(panel);
        for (const child of panel.children) observer.observe(child);
        restore();
      };
      const mutations = new MutationObserver(observeChildren);
      mutations.observe(panel, { childList: true });
      observeChildren();
      cleanup = () => { observer.disconnect(); mutations.disconnect(); };
    });
    return () => { cancelled = true; restoringScroll = false; cleanup(); };
  });

  function resize(value: number): void {
    collapsed = false;
    requestedHeight = Math.min(maxHeight, Math.max(minHeight, value));
  }
  function startResize(event: PointerEvent): void {
    if (event.button !== 0) return;
    event.preventDefault();
    drag = { pointer: event.pointerId, y: event.clientY, height: panelHeight };
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }
  function moveResize(event: PointerEvent): void {
    if (drag?.pointer === event.pointerId) resize(drag.height + drag.y - event.clientY);
  }
  function endResize(event: PointerEvent): void {
    if (drag?.pointer !== event.pointerId) return;
    drag = null;
    const target = event.currentTarget as HTMLElement;
    if (target.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId);
  }
  function resizeByKey(event: KeyboardEvent): void {
    const values: Record<string, number> = { ArrowUp: panelHeight + 24, ArrowDown: panelHeight - 24, Home: minHeight, End: maxHeight };
    if (!(event.key in values)) return;
    event.preventDefault();
    resize(values[event.key]);
  }
  const advanced = $derived(selected === "advanced");
  function openAdvanced(): void {
    selected = "advanced";
    collapsed = false;
  }
</script>

<section bind:this={dock} id={dockId} aria-label="Simulation results" hidden={!open} onscrollcapture={rememberScroll}
  class="relative min-h-0 shrink-0 border-t border-slate-700 bg-slate-900 {open ? 'flex flex-col' : 'hidden'}"
  style:height={collapsed ? "auto" : `${panelHeight}px`}>
  {#if !collapsed}
  <!-- WAI-ARIA window splitter: a focusable separator is an interactive range widget. -->
  <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
  <div role="separator" aria-label="Resize simulation panel" aria-orientation="horizontal" aria-controls={dockId}
    aria-valuemin={Math.round(minHeight)} aria-valuemax={Math.round(maxHeight)} aria-valuenow={panelHeight} aria-valuetext={`${panelHeight} pixels high`} tabindex="0"
    class="absolute inset-x-0 top-0 z-10 flex h-2 touch-none select-none items-center justify-center cursor-row-resize hover:bg-slate-800 focus-visible:bg-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400"
    onpointerdown={startResize} onpointermove={moveResize} onpointerup={endResize} onpointercancel={endResize} onlostpointercapture={() => { drag = null; }} onkeydown={resizeByKey}>
    <span aria-hidden="true" class="h-0.5 w-10 rounded-full bg-slate-600"></span>
  </div>
  {/if}
  <Tabs.Root value={collapsed ? "" : selected} onValueChange={(value) => { if (value) { selected = value; collapsed = false; } }} class="flex min-h-0 flex-1 flex-col">
    <div class="flex shrink-0 items-stretch border-slate-700 {collapsed ? 'h-9' : 'h-11 border-b'}">
      <Tabs.List aria-label="Simulation views" class="flex min-w-0 flex-1 items-stretch overflow-x-auto px-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {#each results as result (result.id)}
          <Tabs.Trigger value={result.id} onclick={() => { selected = result.id; collapsed = false; }} class="relative flex h-full shrink-0 items-center justify-center whitespace-nowrap px-3 text-xs text-slate-400 after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-transparent hover:text-slate-100 data-[state=active]:text-emerald-300 data-[state=active]:after:bg-emerald-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400"><span class="block leading-none">{result.label}</span></Tabs.Trigger>
        {/each}
      </Tabs.List>
      <button type="button" onclick={openAdvanced} aria-pressed={advanced}
        class="flex shrink-0 items-center gap-1 self-center rounded px-2 py-1 text-xs text-slate-500 hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400"
        title="Restricted material-coupled DC analysis"><FlaskConical size={12} aria-hidden="true" />Advanced</button>
      <button type="button" aria-label={collapsed ? "Expand simulation panel" : "Collapse simulation panel"} aria-expanded={!collapsed} aria-controls={`${dockId}-content`} onclick={() => (collapsed = !collapsed)} class="flex w-11 shrink-0 items-center justify-center self-stretch text-slate-400 hover:bg-slate-800 hover:text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">
        {#if collapsed}<ChevronUp size={16} aria-hidden="true" />{:else}<ChevronDown size={16} aria-hidden="true" />{/if}
      </button>
    </div>
    <div id={`${dockId}-content`} hidden={collapsed} class="min-h-0 flex-1 flex-col {collapsed ? 'hidden' : 'flex'}">
    {#if selected !== "move"}
      <div class="flex shrink-0 flex-wrap items-center gap-3 border-b border-slate-700 px-3 py-2 text-xs text-slate-300" aria-label="Simulation run controls">
        <button type="button" onclick={onRun} disabled={!active || !canRun || loading || !onRun}
          class="rounded border border-emerald-600 px-3 py-1.5 text-emerald-200 hover:bg-emerald-950 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">{loading ? "Running simulations…" : "Run simulations"}</button>
        <label class="flex items-center gap-2"><input type="checkbox" bind:checked={autoSimulation} class="accent-emerald-400" /> Auto-run on edits</label>
        <p role="status">{!canRun ? "Resolve the design and coil-end warnings to run." : loading ? "Calculating the active geometry." : sweep ? "Results for the active geometry." : "Run to calculate thrust over travel, friction and stack height."}</p>
      </div>
    {/if}
    <Tabs.Content value="move" data-dock-panel="move" class="min-h-0 flex-1 overflow-auto p-3">
      {@render warnings()}
      <MovePowerPanel input={powerInput} {config} {designName} {onOpenFieldSettings} />
    </Tabs.Content>
    <Tabs.Content value="force" data-dock-panel="force" class="min-h-0 flex-1 overflow-auto p-3">
      {@render warnings()}
      <ForcePanel {config} {sweep} {friction} {height} {drive} {driveError} onConfigureWinding={(cadGeometry ? cadGeometry.terminal_connection === "delta" : config.generatorConnection === "delta" || (!config.generatorEndType && usesDeltaConnection(config.toIpc()))) ? onConfigureWinding : undefined} />
    </Tabs.Content>
    <Tabs.Content value="fields" data-dock-panel="fields" class="min-h-0 flex-1 overflow-auto p-3">
      {@render warnings()}
      <FieldsPanel {config} active={active && open && !collapsed && selected === "fields"} {onOpenFieldSettings} />
    </Tabs.Content>
    <Tabs.Content value="advanced" data-dock-panel="advanced" class="min-h-0 flex-1 overflow-auto p-3">
      <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 class="text-sm font-semibold text-slate-100">Advanced analysis</h2>
          <p class="text-xs text-slate-400">Material-coupled DC force at one fixed magnet position. Separate scope and admission from the move estimate.</p>
        </div>
        <button type="button" onclick={() => { selected = "move"; }} class="rounded border border-slate-600 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Back to move and power</button>
      </div>
      <DcCouplingPanel {config} {cadGeometry} active={active && open && !collapsed && selected === "advanced"} />
    </Tabs.Content>
    </div>
  </Tabs.Root>
</section>

{#snippet warnings()}
  {#if cadGeometry}
    {#if coilEnds && coilEnds.unresolved.length}
      <div class="mb-3 rounded border border-rose-500/60 bg-rose-500/10 px-3 py-2 text-xs text-rose-200" role="alert">
        <p class="font-semibold">Coil ends could not be inferred</p>
        <p class="mt-1">Select the driver end and opposite end for {coilEnds.unresolved.join(", ")} to continue.</p>
        {#if onSelectEnds}<button type="button" onclick={onSelectEnds} class="mt-2 rounded border border-rose-400/60 px-2 py-1 hover:bg-rose-500/20">Select coil ends</button>{/if}
      </div>
    {:else if coilEnds && coilEnds.pending.length}
      <div class="mb-3 rounded border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-xs text-amber-200" role="status" aria-label="Inferred coil ends">
        <p class="font-semibold">Coil ends inferred</p>
        <p class="mt-1">Use these ends, or review which end connects to the driver.</p>
        <div class="mt-2 flex gap-2">
          {#if onUseInferredEnds}<button type="button" onclick={onUseInferredEnds} class="rounded border border-amber-400/60 px-2 py-1 hover:bg-amber-500/20">Use inferred ends</button>{/if}
          {#if onSelectEnds}<button type="button" onclick={onSelectEnds} class="rounded border border-slate-600 px-2 py-1 hover:bg-slate-800">Review</button>{/if}
        </div>
      </div>
    {:else if cadMappingProblems(cadGeometry, config.phases, config.min_trace_mm).length}
      <div class="mb-3 rounded border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-xs text-amber-200" role="alert">
        <p>Update the imported geometry before simulating.</p>
        <ul>{#each cadMappingProblems(cadGeometry, config.phases, config.min_trace_mm) as problem (problem)}<li>{problem}</li>{/each}</ul>
      </div>
    {/if}
  {/if}
  {#if error}<div class="mb-3 rounded border border-rose-500/60 bg-rose-500/10 px-3 py-2 text-xs text-rose-200" role="alert" aria-live="polite">Computation error: {error}</div>{/if}
{/snippet}
