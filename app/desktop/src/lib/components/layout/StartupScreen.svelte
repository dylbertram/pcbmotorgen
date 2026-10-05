<script lang="ts">
  import { importCadDxf, pickCadDxfPath } from "../../ipc";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { ProjectStore } from "../../stores/project.svelte";
  import type { RecentFilesStore } from "../../stores/recentFiles.svelte";
  import { layerOptions as getLayerOptions, nearestLayer, patternLayerRange } from "../../layerConstraints";
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

  type Screen = "home" | "setup" | "recent";
  type GeometrySource = "generated" | "import";

  let screen = $state<Screen>("home");
  let source = $state<GeometrySource>("generated");
  let selectedPattern = $state("");
  let selectedLayers = $state(4);
  let busy = $state(false);
  let error = $state<string | null>(null);
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

  function baseName(path: string): string {
    return path.slice(Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\")) + 1);
  }

  function startSetup(nextSource: GeometrySource): void {
    error = null;
    source = nextSource;
    selectedPattern = config.routing_pattern;
    selectedLayers = config.num_layers;
    screen = "setup";
  }

  function updatePattern(value: string): void {
    selectedPattern = value;
    const pattern = config.routing_patterns.find((item) => item.id === value);
    const choices = getLayerOptions(config.max_layers, patternLayerRange(pattern));
    if (choices.length > 0 && !choices.includes(selectedLayers)) {
      selectedLayers = nearestLayer(selectedLayers, choices);
    }
  }

  async function finishSetup(): Promise<void> {
    if (busy) return;
    busy = true;
    error = null;
    try {
      if (source === "generated") {
        config.routing_pattern = selectedPattern;
        config.num_layers = selectedLayers;
        await config.loadRoutingParams(selectedPattern);
        config.constrainLayersToPattern();
        projects.setCadGeometry(null);
        onComplete();
        return;
      }

      const path = await pickCadDxfPath();
      if (!path) return;
      config.num_layers = selectedLayers;
      const imported = await importCadDxf(
        path,
        1,
        0.05,
        config.min_trace_mm,
        selectedLayers,
        config.pcb_thickness_mm,
      );
      projects.setCadGeometry(imported.geometry);
      if (imported.warnings.length > 0) {
        projects.notice = `Imported ${baseName(path)} with ${imported.warnings.length} warning(s). Review the CAD import diagnostics in Design.`;
      }
      onComplete();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }

  async function openRecent(path: string): Promise<void> {
    if (busy) return;
    busy = true;
    error = null;
    try {
      if (await projects.openPath(path)) onComplete();
      else if (projects.error) error = projects.error;
    } finally {
      busy = false;
    }
  }

  async function browseProject(): Promise<void> {
    if (busy) return;
    busy = true;
    error = null;
    try {
      if (await projects.open()) onComplete();
      else if (projects.error) error = projects.error;
    } finally {
      busy = false;
    }
  }
</script>

<div bind:this={backdropRef} class="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-sm" role="presentation">
  <div
    bind:this={dialogRef}
    class="max-h-[calc(100vh-2rem)] w-full max-w-3xl overflow-y-auto overscroll-contain rounded-xl border border-slate-700 bg-slate-900 shadow-2xl shadow-black/50"
    role="dialog"
    aria-modal="true"
    aria-labelledby="startup-title"
    tabindex="-1"
  >
    <header class="border-b border-slate-800 px-6 py-5">
      <p class="text-[10px] font-semibold uppercase tracking-[0.24em] text-emerald-400">pcbmotorgen</p>
      <h1 id="startup-title" class="mt-1 text-xl font-semibold text-slate-100">
        {screen === "home" ? "Start a design" : screen === "setup" ? "New design setup" : "Open a recent design"}
      </h1>
      <p class="mt-1 text-sm text-slate-400">
        {#if screen === "home"}
          Import CAD geometry, continue a recent project, or configure a new motor design.
        {:else if screen === "setup"}
          Choose the board stack and how trace geometry will be created.
        {:else}
          Select a recent project or browse for a project file.
        {/if}
      </p>
    </header>

    <div class="space-y-4 px-6 py-5">
      {#if screen === "home"}
        <div class="grid gap-3 md:grid-cols-3">
          <button type="button" onclick={() => startSetup("import")} class="group rounded-lg border border-slate-700 bg-slate-800/60 p-4 text-left transition hover:border-sky-500/70 hover:bg-slate-800">
            <span class="mb-3 flex h-9 w-9 items-center justify-center rounded-md bg-sky-500/15 text-lg text-sky-300" aria-hidden="true">↗</span>
            <span class="block text-sm font-semibold text-slate-100">Import CAD</span>
            <span class="mt-1 block text-xs leading-relaxed text-slate-400">Bring in 3D DXF trace centerlines and vias.</span>
          </button>
          <button type="button" onclick={() => (screen = "recent")} class="group rounded-lg border border-slate-700 bg-slate-800/60 p-4 text-left transition hover:border-emerald-500/70 hover:bg-slate-800">
            <span class="mb-3 flex h-9 w-9 items-center justify-center rounded-md bg-emerald-500/15 text-lg text-emerald-300" aria-hidden="true">◷</span>
            <span class="block text-sm font-semibold text-slate-100">Load Recent</span>
            <span class="mt-1 block text-xs leading-relaxed text-slate-400">Resume one of your recent project files.</span>
          </button>
          <button type="button" onclick={() => startSetup("generated")} class="group rounded-lg border border-slate-700 bg-slate-800/60 p-4 text-left transition hover:border-violet-500/70 hover:bg-slate-800">
            <span class="mb-3 flex h-9 w-9 items-center justify-center rounded-md bg-violet-500/15 text-lg text-violet-300" aria-hidden="true">＋</span>
            <span class="block text-sm font-semibold text-slate-100">New Design</span>
            <span class="mt-1 block text-xs leading-relaxed text-slate-400">Set up layers, units, and generated or imported geometry.</span>
          </button>
        </div>
      {:else if screen === "setup"}
        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block text-xs font-medium text-slate-300" for="startup-units">
            Units
            <input id="startup-units" value="Millimetres (mm)" disabled class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-slate-400 disabled:cursor-not-allowed" />
          </label>
          <label class="block text-xs font-medium text-slate-300" for="startup-layers">
            Copper layers
            <select id="startup-layers" value={String(selectedLayers)} onchange={(event) => (selectedLayers = Number(event.currentTarget.value))} disabled={layerChoices.length === 0} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 disabled:opacity-50">
              {#each layerChoices as layer (layer)}<option value={layer}>{layer} layers</option>{/each}
              {#if layerChoices.length === 0}<option value={selectedLayers}>{selectedLayers} layers</option>{/if}
            </select>
          </label>
        </div>

        <fieldset class="space-y-2">
          <legend class="mb-2 text-xs font-medium text-slate-300">Trace geometry</legend>
          <label class="flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2.5 {source === 'generated' ? 'border-emerald-500/60 bg-emerald-500/5' : 'border-slate-700 bg-slate-950/40'}">
            <input type="radio" name="startup-source" value="generated" checked={source === "generated"} onchange={() => (source = "generated")} class="mt-0.5 accent-emerald-500" />
            <span><span class="block text-sm text-slate-100">Generate from a routing pattern</span><span class="text-xs text-slate-400">Create trace geometry from the selected generator.</span></span>
          </label>
          <label class="flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2.5 {source === 'import' ? 'border-sky-500/60 bg-sky-500/5' : 'border-slate-700 bg-slate-950/40'}">
            <input type="radio" name="startup-source" value="import" checked={source === "import"} onchange={() => (source = "import")} class="mt-0.5 accent-sky-500" />
            <span><span class="block text-sm text-slate-100">Import CAD centerlines</span><span class="text-xs text-slate-400">Choose a DXF file after confirming these settings.</span></span>
          </label>
        </fieldset>

        {#if source === "generated"}
          <label class="block text-xs font-medium text-slate-300" for="startup-pattern">
            Routing pattern
            <select id="startup-pattern" value={selectedPattern} onchange={(event) => updatePattern(event.currentTarget.value)} class="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100">
              {#each config.routing_patterns as pattern (pattern.id)}<option value={pattern.id}>{pattern.display_name}</option>{/each}
              {#if config.routing_patterns.length === 0}<option value={config.routing_pattern}>{config.routing_pattern}</option>{/if}
            </select>
          </label>
        {/if}
      {:else}
        {#if recentLoading}
          <p class="rounded-md border border-slate-700 bg-slate-950/50 px-3 py-4 text-sm text-slate-400">Loading recent projects…</p>
        {:else if recentFiles.paths.length === 0}
          <p class="rounded-md border border-slate-700 bg-slate-950/50 px-3 py-4 text-sm text-slate-400">No recent project files yet.</p>
        {:else}
          <ul class="max-h-72 space-y-1 overflow-y-auto pr-1" aria-label="Recent project files">
            {#each recentFiles.paths as path (path)}
              <li>
                <button type="button" onclick={() => void openRecent(path)} disabled={busy} class="flex w-full items-center justify-between gap-4 rounded-md px-3 py-2 text-left hover:bg-slate-800 disabled:opacity-50">
                  <span class="truncate text-sm text-slate-100">{baseName(path)}</span>
                  <span class="shrink-0 truncate text-xs text-slate-500">{path}</span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
        <button type="button" onclick={browseProject} disabled={busy} class="rounded-md border border-slate-600 px-3 py-2 text-xs text-slate-200 hover:border-emerald-500/60 disabled:opacity-50">Browse for project…</button>
      {/if}

      {#if error}
        <p role="alert" class="rounded-md border border-rose-500/50 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">{error}</p>
      {/if}
    </div>

    <footer class="flex items-center justify-between border-t border-slate-800 px-6 py-4">
      {#if screen !== "home"}
        <button type="button" onclick={() => { screen = "home"; error = null; }} disabled={busy} class="text-xs text-slate-400 hover:text-slate-100 disabled:opacity-50">Back</button>
      {:else}
        <span class="text-[11px] text-slate-500">Units are currently fixed to millimetres.</span>
      {/if}
      {#if screen === "setup"}
        <button type="button" onclick={finishSetup} disabled={busy} class="rounded-md border border-emerald-500/50 bg-emerald-600/30 px-4 py-2 text-xs font-medium text-emerald-100 hover:bg-emerald-500/40 disabled:opacity-50">{busy ? "Setting up…" : source === "import" ? "Choose DXF…" : "Create design"}</button>
      {/if}
    </footer>
  </div>
</div>
