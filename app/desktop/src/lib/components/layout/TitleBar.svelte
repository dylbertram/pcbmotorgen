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
  }: {
    projects: ProjectStore;
    loading: boolean;
    drc: DrcController;
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
   the title reads as centered on the lights. The title and project name are
   drag regions; the DRC button and tab strip remain interactive.
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
  <div class="min-w-0 justify-self-center" data-tauri-drag-region="deep">
    <ProjectControls {projects} />
  </div>
  <div class="flex items-center gap-2 justify-self-end pr-4">
    <DrcStatus {drc} cadGeometryActive={projects.cadGeometry !== null} />
    <StatusIndicator {loading} />
  </div>
</div>
