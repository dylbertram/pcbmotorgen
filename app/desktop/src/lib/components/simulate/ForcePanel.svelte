<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { ForceSweepResult } from "../../types";
  import ForceSweepPlot from "./ForceSweepPlot.svelte";

  let { config, sweep, onOpenDriverCheck }: {
    config: ConfigStore;
    sweep: ForceSweepResult | null;
    onOpenDriverCheck?: () => void;
  } = $props();

</script>

<section class="min-w-0 space-y-3" aria-label="Force">
  <header class="space-y-1">
    <h2 class="text-base font-semibold text-slate-100">Force</h2>
    <p class="max-w-3xl text-xs leading-relaxed text-slate-400">
      Thrust over travel at the configured current. This is a static winding result and does not depend on a move. The current is a simulation input, not a supply current or a measured draw.
    </p>
  </header>
  <div class="min-h-64 rounded border border-slate-700 bg-slate-900/40 p-2">
    <ForceSweepPlot result={sweep} />
  </div>
  <div class="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-400">
    <span>At {config.max_current_a.toFixed(2)} A phase amplitude, {config.commutation === "max_thrust" ? "max-thrust commutation" : "phase A only"}.</span>
    <button type="button" onclick={onOpenDriverCheck} disabled={!onOpenDriverCheck}
      class="text-sky-300 underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400 disabled:opacity-40">Open driver calculator</button>
  </div>
</section>
