<script lang="ts">
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import { applyViewMenuAction, VIEW_MENU_GROUPS } from "../../viewMenu";
  let { view }: { view: CoilPreviewViewState } = $props();
</script>

<div role="group" aria-label="Viewport view" class="inline-flex max-w-full flex-wrap justify-start rounded-md border border-slate-700 bg-slate-900/95 p-0.5 text-xs text-slate-300 shadow-sm">
  {#each VIEW_MENU_GROUPS[0] as item (item.id)}
    <button type="button" aria-label={item.id === "view:3d" ? "3D fields and heat" : item.label}
      aria-pressed={view.viewMode === item.value} onclick={() => applyViewMenuAction(view, item.id)}
      class="whitespace-nowrap rounded px-2 py-1.5 sm:px-2.5 hover:bg-slate-800 aria-pressed:bg-slate-800 aria-pressed:font-semibold aria-pressed:text-emerald-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500">
      {#if item.id === "view:3d"}<span class="hidden sm:inline">{item.label}</span><span class="sm:hidden">3D</span>{:else}{item.label}{/if}
    </button>
  {/each}
</div>
