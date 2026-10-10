<script lang="ts">
  import { Dialog } from "bits-ui";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { ProjectStore } from "../../stores/project.svelte";
  import type { DrcController } from "../../stores/drc.svelte";
  import KicadPanel from "../export/KicadPanel.svelte";

  let { open = $bindable(false), config, projects, drc }: {
    open: boolean;
    config: ConfigStore;
    projects: ProjectStore;
    drc: DrcController;
  } = $props();
</script>

<Dialog.Root bind:open>
  <Dialog.Portal>
    <Dialog.Overlay class="fixed inset-0 z-[120] bg-slate-950/80 backdrop-blur-sm" />
    <Dialog.Content class="fixed left-1/2 top-1/2 z-[121] flex max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-3xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900 text-slate-100 shadow-2xl focus:outline-none">
      <header class="flex shrink-0 items-start justify-between gap-4 border-b border-slate-800 px-5 py-4">
        <div>
          <Dialog.Title class="text-lg font-semibold">Send to KiCad</Dialog.Title>
          <Dialog.Description class="mt-1 text-xs text-slate-400">Connect to an open board, review the placement details, then write the geometry.</Dialog.Description>
        </div>
        <Dialog.Close class="rounded-md px-3 py-2 text-xs text-slate-400 hover:bg-slate-800 hover:text-slate-100 focus-visible:outline focus-visible:outline-emerald-400">Close</Dialog.Close>
      </header>
      <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain p-5">
        {#if projects.cadGeometry}
          <p role="status" class="rounded-md border border-amber-500/50 bg-amber-500/10 p-4 text-sm text-amber-100">Imported CAD geometry cannot be sent to KiCad until phase and net mappings are supported. Use File &gt; Export as… &gt; DXF to export this geometry.</p>
        {:else}
          <KicadPanel
            {config}
            drcViolations={drc.violations}
            drcLoading={drc.loading}
            drcError={drc.error}
            drcReady={drc.ready}
            drcLayoutKey={drc.currentLayoutKey}
          />
        {/if}
      </div>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
