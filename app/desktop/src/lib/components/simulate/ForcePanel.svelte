<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { DriveAnalysis, ForceSweepResult } from "../../types";
  import ForceSweepPlot from "./ForceSweepPlot.svelte";

  let { config, sweep, drive = null, onOpenDriverCheck }: {
    config: ConfigStore;
    sweep: ForceSweepResult | null;
    drive?: DriveAnalysis | null;
    onOpenDriverCheck?: () => void;
  } = $props();

  const checkSummary = $derived.by(() => {
    if (!drive) return null;
    const count = (status: "fail" | "warn" | "unknown") => drive.checks.filter(c => c.status === status).length;
    if (count("fail")) return { tone: "text-rose-300", text: `${count("fail")} driver check${count("fail") === 1 ? "" : "s"} fail at the configured current` };
    if (count("warn")) return { tone: "text-amber-300", text: `${count("warn")} driver check${count("warn") === 1 ? "" : "s"} have little margin` };
    if (count("unknown")) return { tone: "text-slate-400", text: `${count("unknown")} driver check${count("unknown") === 1 ? "" : "s"} not evaluated` };
    return { tone: "text-emerald-300", text: "Driver checks pass at the configured current" };
  });
</script>

<section class="min-w-0 space-y-3" aria-label="Force">
  <header class="space-y-1">
    <h2 class="text-base font-semibold text-slate-100">Force</h2>
    <p class="max-w-3xl text-xs leading-relaxed text-slate-400">
      Thrust over travel at the configured current. This is a static winding result and does not depend on a move. The current is a simulation input, not a supply current or a measured draw.
    </p>
  </header>
  <div class="h-64 min-h-40 rounded border border-slate-700 bg-slate-900/40 p-2">
    <ForceSweepPlot result={sweep} embedded />
  </div>
  <div class="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-400">
    <span>At {config.max_current_a.toFixed(2)} A phase amplitude, {config.commutation === "max_thrust" ? "max-thrust commutation" : "phase A only"}.</span>
    {#if checkSummary}<span class={checkSummary.tone}>{checkSummary.text}</span>{/if}
    <button type="button" onclick={onOpenDriverCheck} disabled={!onOpenDriverCheck}
      class="text-sky-300 underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400 disabled:opacity-40">Open driver check</button>
  </div>
</section>
