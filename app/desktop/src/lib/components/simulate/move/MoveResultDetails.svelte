<script lang="ts">
  import type { MoveSummary, MoveCheckStatus } from "../../../move/moveSummary";
  import type { NativeMoveResult } from "../../../types/movePower";
  import MovePowerTrace from "./MovePowerTrace.svelte";

  let { summary, result }: { summary: MoveSummary; result: NativeMoveResult } = $props();

  const statusTone: Record<MoveCheckStatus, string> = {
    pass: "text-emerald-300", warn: "text-amber-300", fail: "text-rose-300", unknown: "text-slate-400",
  };
  const statusText: Record<MoveCheckStatus, string> = { pass: "Pass", warn: "Marginal", fail: "Fail", unknown: "Not evaluated" };
</script>

<div class="flex flex-wrap items-center justify-between gap-2">
  <h3 class="text-sm font-semibold text-slate-100">Power for this move</h3>
  <span class="rounded border px-2 py-0.5 text-[11px] font-semibold {summary.scope === 'Engineering estimate' ? 'border-sky-500/50 bg-sky-500/10 text-sky-200' : 'border-amber-500/50 bg-amber-500/10 text-amber-200'}">{summary.scope}</span>
</div>
<div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
  {#each [["Peak supply draw", summary.headline.peakPower], ["Average during the move", summary.headline.averagePower], ["Energy per move", summary.headline.energy], ["Peak supply current", summary.headline.peakSupplyCurrent]] as [label, value] (label)}
    <div class="rounded border border-slate-700 bg-slate-800/50 px-3 py-2">
      <div class="font-mono text-xl text-slate-100">{value}</div>
      <div class="text-[11px] leading-snug text-slate-400">{label}</div>
    </div>
  {/each}
</div>
<p class="text-xs leading-relaxed text-slate-400">{summary.scopeText}</p>
<div class="grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
  <div class="rounded border border-slate-700 bg-slate-900/40 p-2">
    <h4 class="px-1 pb-1 text-xs text-slate-400">Power over time</h4>
    <MovePowerTrace samples={result.result.demand.samples} supply={!!result.result.demand.source} />
  </div>
  <dl class="grid grid-cols-2 content-start gap-x-3 gap-y-1.5 text-xs">
    <dt class="text-slate-400">Distance</dt><dd class="text-right font-mono text-slate-200">{summary.motion.distance}</dd>
    <dt class="text-slate-400">Duration</dt><dd class="text-right font-mono text-slate-200">{summary.motion.duration}</dd>
    <dt class="text-slate-400">Peak speed</dt><dd class="text-right font-mono text-slate-200">{summary.motion.peakSpeed}</dd>
    <dt class="text-slate-400">Peak acceleration</dt><dd class="text-right font-mono text-slate-200">{summary.motion.peakAcceleration}</dd>
    <dt class="text-slate-400">Peak motor force</dt><dd class="text-right font-mono text-slate-200">{summary.motion.peakForce}</dd>
    <dt class="text-slate-400">Phase peak</dt><dd class="text-right font-mono text-slate-200">{summary.electrical.phasePeak}</dd>
    {#if summary.electrical.phasePeakIncludingRipple}
      <dt class="text-slate-400">Phase peak with ripple</dt><dd class="text-right font-mono text-slate-200">{summary.electrical.phasePeakIncludingRipple}</dd>
    {/if}
  </dl>
</div>

<div class="space-y-1.5">
  {#each summary.checks as check (check.label)}
    <div class="flex items-start gap-2 text-xs">
      <span class="mt-0.5 w-16 shrink-0 font-semibold {statusTone[check.status]}">{statusText[check.status]}</span>
      <div class="min-w-0">
        <span class="text-slate-200">{check.label}:</span> <span class="font-mono text-slate-300">{check.reading}</span>
        {#if check.status !== "pass"}<p class="mt-0.5 leading-snug text-slate-400">{check.detail}</p>{/if}
      </div>
    </div>
  {/each}
</div>

{#if summary.exclusions.length || summary.omissions.length}
  <details class="rounded border border-amber-500/30 bg-amber-500/5 p-2.5 text-xs">
    <summary class="cursor-pointer text-amber-200">What this estimate leaves out ({summary.exclusions.length + summary.omissions.length})</summary>
    <ul class="mt-1.5 space-y-1 text-amber-100/80">
      {#each summary.exclusions as item (item)}<li>{item}</li>{/each}
      {#each summary.omissions as item (item)}<li>{item}</li>{/each}
    </ul>
  </details>
{/if}
