<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { DriveAnalysis, ForceSweepResult, FrictionBudgetDto, HeightStackResultDto } from "../../types";
  import ForceSweepPlot from "./ForceSweepPlot.svelte";
  import DriverSuitability from "./DriverSuitability.svelte";

  let { config, sweep, friction, height, drive = null, driveError = null, onConfigureWinding }: {
    config: ConfigStore;
    sweep: ForceSweepResult | null;
    friction: FrictionBudgetDto | null;
    height: HeightStackResultDto | null;
    drive?: DriveAnalysis | null;
    driveError?: string | null;
    onConfigureWinding?: () => void;
  } = $props();

  const netThrust = $derived(sweep && friction ? sweep.mean_thrust_n - friction.total_n : null);
  const current = $derived(config.max_current_a);
  const metric = (value: number | null | undefined, digits = 3) => value === null || value === undefined ? "—" : value.toFixed(digits);
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

  <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
    <span>Net of friction:
      <span class="font-mono {netThrust !== null && netThrust <= 0 ? 'text-rose-300' : 'text-slate-100'}">{metric(netThrust)} N</span>
    </span>
    <span>At {current.toFixed(2)} A phase amplitude, {config.commutation === "max_thrust" ? "max-thrust commutation" : "phase A only"}.</span>
    <span class="text-slate-500">The move tab calculates the current a specific motion actually needs.</span>
    {#if checkSummary}<span class={checkSummary.tone}>{checkSummary.text}</span>{/if}
  </div>

  <details class="rounded border border-slate-700 bg-slate-800/40 p-3">
    <summary class="cursor-pointer text-xs text-slate-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Winding and driver checks at this current</summary>
    <div class="mt-3">
      <DriverSuitability analysis={drive} error={driveError} {onConfigureWinding} embedded />
    </div>
  </details>

  <div class="grid gap-2 text-xs sm:grid-cols-2">
    <details class="rounded border border-slate-700 bg-slate-800/40 p-3">
      <summary class="cursor-pointer text-slate-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Friction budget</summary>
      {#if friction}
        <dl class="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 font-mono">
          <dt class="text-slate-400">Bearing</dt><dd class="text-right text-slate-100">{(friction.bearing_friction_n * 1000).toFixed(1)} mN</dd>
          <dt class="text-slate-400">Cable drag</dt><dd class="text-right text-slate-100">{(friction.cable_drag_n * 1000).toFixed(1)} mN</dd>
          <dt class="text-slate-400">Wiper</dt><dd class="text-right text-slate-100">{(friction.wiper_contact_n * 1000).toFixed(1)} mN</dd>
          <dt class="text-slate-400">Detent</dt><dd class="text-right text-slate-100">{(friction.cogging_n * 1000).toFixed(1)} mN</dd>
          <dt class="text-slate-400">Total</dt><dd class="text-right text-amber-300">{(friction.total_n * 1000).toFixed(1)} mN</dd>
        </dl>
      {:else}<p class="mt-2 text-slate-500">Run the simulation to read the friction budget.</p>{/if}
    </details>
    <details class="rounded border border-slate-700 bg-slate-800/40 p-3">
      <summary class="cursor-pointer text-slate-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Stack height</summary>
      {#if height}
        <dl class="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 font-mono">
          <dt class="text-slate-400">PCB</dt><dd class="text-right text-slate-100">{(height.pcb_thickness_m * 1000).toFixed(2)} mm</dd>
          <dt class="text-slate-400">Air gap</dt><dd class="text-right text-slate-100">{(height.air_gap_m * 1000).toFixed(2)} mm</dd>
          <dt class="text-slate-400">Magnet</dt><dd class="text-right text-slate-100">{(height.magnet_height_m * 1000).toFixed(2)} mm</dd>
          <dt class="text-slate-400">Total</dt><dd class="text-right text-emerald-300">{(height.total_height_m * 1000).toFixed(2)} mm</dd>
        </dl>
      {:else}<p class="mt-2 text-slate-500">Run the simulation to read the stack height.</p>{/if}
    </details>
  </div>
</section>
