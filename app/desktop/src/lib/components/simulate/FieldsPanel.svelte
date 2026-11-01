<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import FluxDiagram from "./FluxDiagram.svelte";

  let { config, active, onOpenFieldSettings }: {
    config: ConfigStore;
    active: boolean;
    onOpenFieldSettings?: () => void;
  } = $props();
</script>

<section class="min-w-0 space-y-3" aria-label="Fields">
  <header class="space-y-1">
    <h2 class="text-base font-semibold text-slate-100">Fields</h2>
    <p class="max-w-3xl text-xs leading-relaxed text-slate-400">
      Magnet field through the cross-section at the current design. The 3D view and copper-loss settings stay in the viewport rail.
    </p>
  </header>

  <div class="h-72 min-h-40 rounded border border-slate-700 bg-slate-900/40 p-2">
    <FluxDiagram {config} {active} embedded />
  </div>

  <div class="flex flex-wrap items-center gap-3 text-xs text-slate-400">
    {#if onOpenFieldSettings}
      <button type="button" onclick={onOpenFieldSettings}
        class="rounded border border-slate-600 px-3 py-1.5 text-slate-200 hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Field and loss settings</button>
    {/if}
    <p class="max-w-2xl leading-relaxed">Copper loss shows cycle-average I²R in W/m. It is not a temperature prediction, and separate field sources are not combined into one coupled solve.</p>
  </div>
</section>
