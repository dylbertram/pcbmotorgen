<script lang="ts">
  import type { DriveAnalysis } from "../../types";

  let { analysis }: { analysis: DriveAnalysis } = $props();

  function amps(value: number): string {
    return Number.isFinite(value) ? `${value.toFixed(2)} A` : "Not available";
  }
</script>

<div class="rounded-md border border-slate-700 bg-slate-900/50 px-3 py-2.5">
  <h4 class="text-xs font-semibold text-slate-200">Current requirements at the selected operating point</h4>
  <dl class="mt-2 space-y-2 text-xs">
    <div class="flex flex-wrap justify-between gap-x-3">
      <dt class="text-slate-400">Selected phase current, before PWM ripple</dt>
      <dd class="font-mono text-slate-100">{amps(analysis.phase_current_a)}</dd>
    </div>
    {#each analysis.phases as phase (phase.net)}
      <div class="flex flex-wrap justify-between gap-x-3">
        <dt class="text-slate-400">{phase.net} terminal peak, including PWM ripple</dt>
        <dd class="font-mono text-slate-100">{phase.connected ? amps(analysis.peak_current_a) : "Open circuit"}</dd>
      </div>
    {/each}
    <div class="flex flex-wrap justify-between gap-x-3">
      <dt class="text-slate-400">PWM ripple, peak-to-peak per phase</dt>
      <dd class="font-mono text-slate-100">{amps(analysis.ripple_pp_a)}</dd>
    </div>
    <div class="flex flex-wrap justify-between gap-x-3">
      <dt class="text-slate-400">DC supply peak at {analysis.bus_voltage_v.toFixed(1)} V</dt>
      <dd class="text-slate-300">Not calculated</dd>
    </div>
  </dl>
  <p class="mt-2 text-[11px] leading-snug text-slate-400">
    Terminal peaks are current magnitudes, not simultaneous draws from the supply.
    Each peak is the selected current plus half the estimated PWM ripple.
    These estimates do not mean the driver checks pass.
  </p>
  <p class="mt-2 text-[11px] leading-snug text-slate-400">
    For supply sizing, do not multiply the phase current by the bus voltage or add the terminal peaks.
    DC input draw depends on PWM duty, speed, load and driver losses. Supply transients and regeneration are not modeled.
  </p>
</div>
