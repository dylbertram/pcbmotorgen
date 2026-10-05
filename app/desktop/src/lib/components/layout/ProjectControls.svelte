<script lang="ts">
  import type { ProjectStore } from "../../stores/project.svelte";

  let { projects }: { projects: ProjectStore } = $props();
</script>

<!--
  Project file affordance: the active project name plus the dirty-state
  indicator. Open / Save / Save As / Import CAD live in the native File
  menu (src-tauri/src/menu.rs → bindProjectMenuActions in App.svelte);
  the store owns the flows.
-->
<div
  class="flex max-w-[280px] items-center gap-1.5 text-xs text-slate-300"
  aria-label="Project file"
  title={projects.currentPath ?? "Not saved yet — use Save As"}
>
  <span class="truncate">{projects.label}</span>
  {#if projects.isDirty}
    <span
      class="text-amber-400"
      title="Unsaved changes"
      aria-label="Unsaved changes"
    >●</span>
  {/if}
</div>
