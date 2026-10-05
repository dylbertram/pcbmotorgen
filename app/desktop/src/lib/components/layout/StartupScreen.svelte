<script lang="ts">
  import { importCadDxf, loadProject, pickCadDxfPath } from "../../ipc";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { ProjectStore } from "../../stores/project.svelte";
  import type { RecentFilesStore } from "../../stores/recentFiles.svelte";
  import type { ProjectState } from "../../types";
  import {
    layerOptions as getLayerOptions,
    nearestLayer,
    patternLayerRange,
  } from "../../layerConstraints";
  import { attachBackdropScrollGuard, lockPageScroll } from "../../utils/pageScrollLock";

  let {
    config,
    projects,
    recentFiles,
    recentLoading,
    onComplete,
  }: {
    config: ConfigStore;
    projects: ProjectStore;
    recentFiles: RecentFilesStore;
    recentLoading: boolean;
    onComplete: () => void;
  } = $props();

  type Screen = "home" | "new" | "import";

  let screen = $state<Screen>("home");
  let selectedPath = $state<string | null>(null);
  let selectedProject = $state<ProjectState | null>(null);
  let selectedPattern = $state("");
  let selectedLayers = $state(4);
  let summaryLoading = $state(false);
  let summaryError = $state<string | null>(null);
  let actionError = $state<string | null>(null);
  let busy = $state(false);
  let inspectionGeneration = 0;
  let backdropRef = $state<HTMLDivElement | undefined>(undefined);
  let dialogRef = $state<HTMLDivElement | undefined>(undefined);

  let layerChoices = $derived.by(() => {
    const pattern = config.routing_patterns.find((item) => item.id === selectedPattern);
    return getLayerOptions(config.max_layers, patternLayerRange(pattern));
  });

  $effect(() => {
    if (!backdropRef || !dialogRef) return;
    const detachGuard = attachBackdropScrollGuard(backdropRef, dialogRef);
    const unlock = lockPageScroll(document);
    dialogRef.focus();
    return () => {
      detachGuard();
      unlock();
    };
  });

  let detailTitle = $derived.by(() => {
    if (screen === "new") return "New design";
    if (screen === "import") return "Import CAD";
    return selectedPath ? baseName(selectedPath) : "Welcome";
  });

  function baseName(path: string): string {
    return path.slice(Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\")) + 1);
  }

  function startNewDesign(): void {
    actionError = null;
    selectedPattern = config.routing_pattern;
    selectedLayers = config.num_layers;
    screen = "new";
  }

  function startImport(): void {
    actionError = null;
    selectedLayers = config.num_layers;
    screen = "import";
  }

  function goHome(): void {
    screen = "home";
    actionError = null;
  }

  function updatePattern(value: string): void {
    selectedPattern = value;
    const pattern = config.routing_patterns.find((item) => item.id === value);
    const choices = getLayerOptions(config.max_layers, patternLayerRange(pattern));
    if (choices.length > 0 && !choices.includes(selectedLayers)) {
      selectedLayers = nearestLayer(selectedLayers, choices);
    }
  }

  async function inspectRecent(path: string): Promise<void> {
    selectedPath = path;
    selectedProject = null;
    summaryError = null;
    summaryLoading = true;
    const generation = ++inspectionGeneration;
    try {
      await recentFiles.dropMissing(path);
      if (!recentFiles.paths.includes(path)) {
        throw new Error("This project file is no longer available.");
      }
      const result = await loadProject(path);
      if (generation === inspectionGeneration) selectedProject = result.project;
    } catch (e) {
      if (generation === inspectionGeneration) {
        summaryError = e instanceof Error ? e.message : String(e);
      }
    } finally {
      if (generation === inspectionGeneration) summaryLoading = false;
    }
  }

  async function openSelectedRecent(): Promise<void> {
    if (!selectedPath || busy) return;
    await openRecent(selectedPath);
  }

  async function openRecent(path: string): Promise<void> {
    if (busy) return;
    inspectionGeneration += 1;
    summaryLoading = false;
    busy = true;
    actionError = null;
    try {
      if (await projects.openPath(path)) onComplete();
      else if (projects.error) actionError = projects.error;
    } finally {
      busy = false;
    }
  }

  async function browseProject(): Promise<void> {
    if (busy) return;
    busy = true;
    actionError = null;
    try {
      if (await projects.open()) onComplete();
      else if (projects.error) actionError = projects.error;
    } finally {
      busy = false;
    }
  }

  async function createDesign(): Promise<void> {
    if (busy) return;
    busy = true;
    actionError = null;
    try {
      config.routing_pattern = selectedPattern;
      config.num_layers = selectedLayers;
      await config.loadRoutingParams(selectedPattern);
      config.constrainLayersToPattern();
      projects.setCadGeometry(null);
      onComplete();
    } catch (e) {
      actionError = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }

  async function importCad(): Promise<void> {
    if (busy) return;
    busy = true;
    actionError = null;
    try {
      const path = await pickCadDxfPath();
      if (!path) return;
      const imported = await importCadDxf(
        path,
        1,
        0.05,
        config.min_trace_mm,
        selectedLayers,
        config.pcb_thickness_mm,
      );
      config.num_layers = selectedLayers;
      projects.setCadGeometry(imported.geometry);
      if (imported.warnings.length > 0) {
        projects.notice = `Imported ${baseName(path)} with ${imported.warnings.length} warning(s). Review the CAD import diagnostics in Design.`;
      }
      onComplete();
    } catch (e) {
      actionError = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }
</script>

<div
  bind:this={backdropRef}
  class="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm"
  role="presentation"
>
  <div
    bind:this={dialogRef}
    class="grid h-[min(680px,calc(100dvh-2rem))] w-full max-w-5xl grid-rows-[minmax(190px,0.8fr)_minmax(0,1.2fr)] overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-2xl shadow-black/50 md:grid-cols-[minmax(230px,0.72fr)_minmax(0,1.7fr)] md:grid-rows-1"
    role="dialog"
    aria-modal="true"
    aria-labelledby="startup-title"
    tabindex="-1"
  >
    <aside class="flex min-h-0 flex-col border-b border-slate-700 bg-slate-950/50 md:border-b-0 md:border-r">
      <header class="shrink-0 px-5 pb-3 pt-5">
        <p class="text-[10px] font-semibold uppercase tracking-[0.24em] text-emerald-400">pcbmotorgen</p>
        <h1 id="startup-title" class="mt-1 text-base font-semibold text-slate-100">Recent projects</h1>
      </header>

      <div class="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {#if recentLoading}
          <p class="rounded-md px-3 py-3 text-xs text-slate-500">Loading recent projects…</p>
        {:else if recentFiles.paths.length === 0}
          <p class="rounded-md px-3 py-3 text-xs text-slate-500">No recent projects yet.</p>
        {:else}
          <ul class="space-y-1" aria-label="Recent project files">
            {#each recentFiles.paths as path (path)}
              <li>
                <button
                  type="button"
                  aria-pressed={selectedPath === path}
                  title={path}
                  onclick={() => void inspectRecent(path)}
                  ondblclick={() => void openRecent(path)}
                  disabled={busy}
                  class="w-full rounded-md px-3 py-2 text-left transition disabled:opacity-50 {selectedPath === path ? 'bg-slate-800 ring-1 ring-emerald-500/50' : 'hover:bg-slate-800/70'}"
                >
                  <span class="block truncate text-sm text-slate-100">{baseName(path)}</span>
                  <span class="mt-0.5 block truncate text-[10px] text-slate-500">{path}</span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </div>

      <div class="shrink-0 space-y-1 border-t border-slate-800 p-3">
        <button type="button" onclick={browseProject} disabled={busy} class="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-xs text-slate-300 hover:bg-slate-800 hover:text-slate-100 disabled:opacity-50">
          <span>Open project…</span><span aria-hidden="true" class="text-slate-500">›</span>
        </button>
        <button type="button" onclick={startNewDesign} disabled={busy} class="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-xs text-slate-300 hover:bg-slate-800 hover:text-slate-100 disabled:opacity-50">
          <span>New design</span><span aria-hidden="true" class="text-slate-500">＋</span>
        </button>
        <button type="button" onclick={startImport} disabled={busy} class="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-xs text-slate-300 hover:bg-slate-800 hover:text-slate-100 disabled:opacity-50">
          <span>Import CAD</span><span aria-hidden="true" class="text-slate-500">↗</span>
        </button>
      </div>
    </aside>

    <main class="flex min-h-0 min-w-0 flex-col">
      <header class="shrink-0 border-b border-slate-800 px-5 py-4 md:px-7 md:py-5">
        <p class="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">Startup</p>
        <h2 class="mt-1 text-lg font-semibold text-slate-100">{detailTitle}</h2>
        <p class="mt-1 text-xs text-slate-400">
          {#if screen === "new"}
            Configure the board stack and generated routing pattern.
          {:else if screen === "import"}
            Select a CAD file to use as the active trace geometry.
          {:else if selectedPath}
            Project overview. Double-click its row or choose Open to continue.
          {:else}
            Select a recent project, or choose an action from the left.
          {/if}
        </p>
      </header>

      <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5 md:px-7">
        {#if screen === "new"}
          <div class="grid gap-4 sm:grid-cols-2">
            <label class="block text-xs font-medium text-slate-300" for="startup-layers">
              Copper layers
              <select id="startup-layers" value={String(selectedLayers)} onchange={(event) => (selectedLayers = Number(event.currentTarget.value))} disabled={layerChoices.length === 0} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 disabled:opacity-50">
                {#each layerChoices as layer (layer)}<option value={layer}>{layer} layers</option>{/each}
                {#if layerChoices.length === 0}<option value={selectedLayers}>{selectedLayers} layers</option>{/if}
              </select>
            </label>
            <label class="block text-xs font-medium text-slate-300" for="startup-pattern">
              Routing pattern
              <select id="startup-pattern" value={selectedPattern} onchange={(event) => updatePattern(event.currentTarget.value)} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100">
                {#each config.routing_patterns as pattern (pattern.id)}<option value={pattern.id}>{pattern.display_name}</option>{/each}
                {#if config.routing_patterns.length === 0}<option value={config.routing_pattern}>{config.routing_pattern}</option>{/if}
              </select>
            </label>
          </div>
          <div class="mt-5 rounded-md border border-slate-700 bg-slate-950/50 p-4">
            <h3 class="text-sm font-medium text-slate-100">Generated design</h3>
            <p class="mt-1 text-xs leading-relaxed text-slate-400">Trace geometry will be created by the selected routing pattern.</p>
          </div>
        {:else if screen === "import"}
          <div class="rounded-md border border-slate-700 bg-slate-950/50 p-4">
            <h3 class="text-sm font-medium text-slate-100">CAD geometry</h3>
            <p class="mt-1 text-xs leading-relaxed text-slate-400">Choose a DXF file. Copper layers are detected from Z heights; the layer count below is used for legacy 2D files.</p>
            <label class="mt-4 block max-w-xs text-xs font-medium text-slate-300" for="import-layer-count">
              Fallback copper layers
              <select id="import-layer-count" value={String(selectedLayers)} onchange={(event) => (selectedLayers = Number(event.currentTarget.value))} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100">
                {#each config.layerOptions as layer (layer)}<option value={layer}>{layer} layers</option>{/each}
              </select>
            </label>
          </div>
        {:else if selectedPath && summaryLoading}
          <p class="rounded-md border border-slate-700 bg-slate-950/50 px-4 py-5 text-sm text-slate-400">Loading project overview…</p>
        {:else if summaryError}
          <p role="alert" class="rounded-md border border-rose-500/50 bg-rose-500/10 px-4 py-3 text-xs text-rose-200">{summaryError}</p>
        {:else if selectedProject}
          <div class="rounded-lg border border-slate-700 bg-slate-950/50 p-4">
            <div class="flex items-center justify-between gap-4">
              <span class="text-xs text-slate-400">Geometry source</span>
              <span class="rounded-full bg-slate-800 px-2.5 py-1 text-xs text-slate-200">{selectedProject.cad_geometry ? "Imported CAD" : "Generated"}</span>
            </div>
            <dl class="mt-4 grid grid-cols-2 gap-x-5 gap-y-3">
              <div><dt class="text-[10px] uppercase tracking-wider text-slate-500">Routing pattern</dt><dd class="mt-0.5 truncate text-sm text-slate-100">{selectedProject.config.routing_pattern}</dd></div>
              <div><dt class="text-[10px] uppercase tracking-wider text-slate-500">Copper layers</dt><dd class="mt-0.5 text-sm text-slate-100">{selectedProject.cad_geometry?.layer_z_mm.length ?? selectedProject.config.num_layers}</dd></div>
              <div><dt class="text-[10px] uppercase tracking-wider text-slate-500">Desired travel</dt><dd class="mt-0.5 text-sm text-slate-100">{selectedProject.config.desired_travel_mm.toFixed(1)} mm</dd></div>
              <div><dt class="text-[10px] uppercase tracking-wider text-slate-500">Board width</dt><dd class="mt-0.5 text-sm text-slate-100">{selectedProject.config.active_area_width_mm.toFixed(1)} mm</dd></div>
              <div><dt class="text-[10px] uppercase tracking-wider text-slate-500">Magnets</dt><dd class="mt-0.5 text-sm text-slate-100">{selectedProject.config.magnet_count}</dd></div>
              <div><dt class="text-[10px] uppercase tracking-wider text-slate-500">Geometry elements</dt><dd class="mt-0.5 text-sm text-slate-100">{selectedProject.cad_geometry ? selectedProject.cad_geometry.routing.segments.length + selectedProject.cad_geometry.routing.curves.length + selectedProject.cad_geometry.routing.vias.length : "Generated from settings"}</dd></div>
            </dl>
          </div>
        {:else if !recentLoading && recentFiles.paths.length === 0}
          <div class="rounded-lg border border-dashed border-slate-700 bg-slate-950/30 px-5 py-8 text-center">
            <p class="text-sm font-medium text-slate-200">No recent projects</p>
            <p class="mt-1 text-xs text-slate-500">Open a project file or start a new design.</p>
          </div>
        {:else}
          <div class="rounded-lg border border-slate-700 bg-slate-950/30 px-5 py-8 text-center">
            <p class="text-sm font-medium text-slate-200">Choose a project to see its overview</p>
            <p class="mt-1 text-xs text-slate-500">Recent projects appear in the list on the left.</p>
          </div>
        {/if}

        {#if actionError}
          <p role="alert" class="mt-3 rounded-md border border-rose-500/50 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">{actionError}</p>
        {/if}
      </div>

      <footer class="flex shrink-0 items-center justify-between border-t border-slate-800 px-5 py-3 md:px-7">
        {#if screen !== "home"}
          <button type="button" onclick={goHome} disabled={busy} class="text-xs text-slate-400 hover:text-slate-100 disabled:opacity-50">Back</button>
        {:else}
          <span class="text-[11px] text-slate-500">pcbmotorgen</span>
        {/if}
        {#if screen === "new"}
          <button type="button" onclick={createDesign} disabled={busy || layerChoices.length === 0} class="rounded-md border border-emerald-500/50 bg-emerald-600/30 px-4 py-2 text-xs font-medium text-emerald-100 hover:bg-emerald-500/40 disabled:opacity-50">{busy ? "Setting up…" : "Create design"}</button>
        {:else if screen === "import"}
          <button type="button" onclick={importCad} disabled={busy} class="rounded-md border border-sky-500/50 bg-sky-600/30 px-4 py-2 text-xs font-medium text-sky-100 hover:bg-sky-500/40 disabled:opacity-50">{busy ? "Importing…" : "Import DXF…"}</button>
        {:else if selectedPath}
          <button type="button" onclick={openSelectedRecent} disabled={busy || summaryLoading || !selectedProject} class="rounded-md border border-emerald-500/50 bg-emerald-600/30 px-4 py-2 text-xs font-medium text-emerald-100 hover:bg-emerald-500/40 disabled:opacity-50">{busy ? "Opening…" : "Open"}</button>
        {/if}
      </footer>
    </main>
  </div>
</div>
