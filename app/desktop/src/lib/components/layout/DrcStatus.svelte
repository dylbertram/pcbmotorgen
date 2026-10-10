<script lang="ts">
  import { Dialog } from "bits-ui";
  import type { DrcController } from "../../stores/drc.svelte";
  import InterferencePanel from "../export/InterferencePanel.svelte";

  let { drc, cadGeometryActive }: { drc: DrcController; cadGeometryActive: boolean } = $props();
  let label = $derived.by(() => {
    if (cadGeometryActive) return "DRC unavailable";
    if (drc.loading) return "DRC checking";
    if (drc.error) return "DRC failed";
    if (!drc.ready) return "DRC pending";
    if (drc.violations.length) return `DRC: ${drc.violations.length} violation${drc.violations.length === 1 ? "" : "s"}`;
    return "DRC clear";
  });
  let color = $derived(cadGeometryActive || drc.loading || !drc.ready ? "text-amber-300" : drc.violations.length ? "text-rose-300" : "text-emerald-300");
</script>

<Dialog.Root>
  <Dialog.Trigger class="rounded px-2 py-1 text-[10px] hover:bg-slate-800 focus-visible:outline focus-visible:outline-emerald-400 {color}" aria-label="Design rule check: {label}">
    {label}
  </Dialog.Trigger>
  <Dialog.Portal>
    <Dialog.Overlay class="fixed inset-0 z-[120] bg-slate-950/80 backdrop-blur-sm" />
    <Dialog.Content class="fixed left-1/2 top-1/2 z-[121] max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto overscroll-contain rounded-xl border border-slate-700 bg-slate-900 p-5 text-slate-100 shadow-2xl focus:outline-none">
      <div class="mb-4 flex items-start justify-between gap-4">
        <div>
          <Dialog.Title class="text-lg font-semibold">Design rule check</Dialog.Title>
          <Dialog.Description class="mt-1 text-xs text-slate-400">Clearance and via-pad checks for the current generated layout.</Dialog.Description>
        </div>
        <Dialog.Close class="rounded-md px-3 py-2 text-xs text-slate-400 hover:bg-slate-800 hover:text-slate-100 focus-visible:outline focus-visible:outline-emerald-400">Close</Dialog.Close>
      </div>
      {#if cadGeometryActive}
        <p role="status" class="text-sm text-amber-200">DRC is not available for imported CAD geometry.</p>
      {:else}
        <InterferencePanel violations={drc.violations} loading={drc.loading} error={drc.error} ready={drc.ready} onCheck={() => drc.request()} />
      {/if}
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
