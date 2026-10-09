<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { ProjectStore } from "../../stores/project.svelte";
  import type { InterferenceViolation } from "../../types";
  import type { ExportTarget } from "../../ui";
  import InterferencePanel from "../export/InterferencePanel.svelte";
  import KicadPanel from "../export/KicadPanel.svelte";
  import DxfPanel from "../export/DxfPanel.svelte";

  let {
    config,
    projects,
    drcViolations,
    drcLoading,
    drcError,
    drcReady,
    drcLayoutKey,
    onCheckDrc,
  }: {
    config: ConfigStore;
    projects: ProjectStore;
    drcViolations: InterferenceViolation[];
    drcLoading: boolean;
    drcError: string | null;
    drcReady: boolean;
    drcLayoutKey: string;
    onCheckDrc: () => void;
  } = $props();

  // Session-only export target; never enters IPC.
  let exportTarget = $state<ExportTarget>("kicad");
</script>

<div class="mb-4 rounded-lg border border-slate-700 bg-slate-800/40 p-4">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <h2 class="text-sm font-semibold text-slate-100">Export design</h2>
      <p class="mt-1 text-xs text-slate-400">
        KiCad IPC writes generated geometry to an open board. 3D DXF exchanges the active centerline geometry with CAD.
      </p>
    </div>
    <label class="text-xs text-slate-300" for="export-target">
      Target
      <select
        id="export-target"
        value={exportTarget}
        onchange={(event) => {
          const target = (event.currentTarget as HTMLSelectElement).value;
          if (target === "kicad" || target === "dxf") exportTarget = target;
        }}
        class="ml-2 rounded-md border border-emerald-500/60 bg-slate-800 px-3 py-1.5 text-sm text-emerald-200 focus:border-emerald-400 focus:outline-none"
      >
        <option value="kicad">KiCad IPC · available</option>
        <option value="dxf">3D DXF · available</option>
        <option value="json" disabled>JSON · planned</option>
        <option value="svg" disabled>SVG · planned</option>
      </select>
    </label>
  </div>
</div>
{#if exportTarget === "kicad"}
{#if projects.cadGeometry}
  <div class="rounded-lg border border-amber-500/50 bg-amber-500/10 p-4 text-sm text-amber-100" role="status">
    Imported CAD geometry is active. KiCad writing is guarded because phase/net electrical semantics are not yet mapped; choose 3D DXF to export this geometry.
  </div>
{:else}
<div class="grid gap-4 xl:grid-cols-2">
  <section class="rounded-lg border border-slate-700 bg-slate-800/40 p-4" aria-label="Design rule check">
    <InterferencePanel
      violations={drcViolations}
      loading={drcLoading}
      error={drcError}
      ready={drcReady}
      onCheck={onCheckDrc}
    />
  </section>
  <KicadPanel
    {config}
    drcViolations={drcViolations}
    drcLoading={drcLoading}
    drcError={drcError}
    drcReady={drcReady}
    drcLayoutKey={drcLayoutKey}
  />
</div>
{/if}
{:else}
<DxfPanel {config} {projects} />
{/if}
