<script lang="ts">
  import type { ProjectStore } from "../../stores/project.svelte";
  import ProjectControls from "./ProjectControls.svelte";
  import StatusIndicator from "./StatusIndicator.svelte";
  import DrcStatus from "./DrcStatus.svelte";
  import type { DrcController } from "../../stores/drc.svelte";

  let {
    projects,
    loading,
    drc,
    onVersions,
    versionsDisabled = false,
  }: {
    projects: ProjectStore;
    loading: boolean;
    drc: DrcController;
    onVersions: () => void;
    versionsDisabled?: boolean;
  } = $props();
</script>

<!--
  Zone 1 of the slim top bar: the native macOS traffic lights (titleBarStyle:
  Overlay) float over its left edge, inset 12.5px from both left and top, with
  ~23px clearance before the app name. The row is 36px tall. Measured on
  macOS 26.6 (calibrated against a real screenshot): trafficLightPosition x
  lands on the button's left edge directly, and the light's center renders at
  y − 2.25 — wry only resizes the title-bar container to button height + y
   and never touches the button's vertical frame, so AppKit's natural rest
  origin.y ≈ 9.25 inside the container wins. y=21.5 therefore puts the light
  center at 19.25, the optical center of the 12px uppercase title glyphs, so
   the title reads as centered on the lights. The app name is a drag region;
   the project title, DRC button and tab strip remain interactive.
-->
<div
  class="grid h-9 grid-cols-[1fr_auto_1fr] items-center"
  data-tauri-drag-region
>
  <div class="pl-[95px]" data-tauri-drag-region="deep">
    <span
      class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400"
    >
      pcbmotorgen
    </span>
  </div>
  <div class="flex min-w-0 items-center gap-2 justify-self-center">
    <ProjectControls {projects} />
    <button type="button" onclick={onVersions} disabled={projects.busy || versionsDisabled} aria-label="Project versions" class="shrink-0 rounded border border-slate-700 bg-slate-800/50 px-2 py-1 text-[11px] text-slate-300 hover:border-emerald-500/50 hover:text-emerald-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400 disabled:opacity-50">{projects.activeVersionId !== null ? `Version ${projects.activeVersionId}` : "Versions"}</button>
  </div>
  <div class="flex items-center gap-2 justify-self-end pr-4">
    <DrcStatus {drc} cadGeometryActive={projects.cadGeometry !== null} />
    <StatusIndicator {loading} />
  </div>
</div>
