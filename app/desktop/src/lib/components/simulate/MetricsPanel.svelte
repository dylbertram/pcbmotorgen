<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type {
    CommutationMode,
    ForceSweepResult,
    FrictionBudgetDto,
    HeightStackResultDto,
    DriveAnalysis,
  } from "../../types";
  import { rippleStatus } from "../../format";
  import HelpTag from "../ui/HelpTag.svelte";
  import CurrentBudget from "./CurrentBudget.svelte";

  // Human-readable labels for the raw `CommutationMode` wire values — the UI
  // must not echo snake_case wire values back to the user.
  const COMMUTATION_LABELS: Record<CommutationMode, string> = {
    max_thrust: "Max thrust (FOC)",
    phase_a_only: "Phase A only",
  };

  const commutationLabel = (mode: CommutationMode): string => COMMUTATION_LABELS[mode];

  let {
    config,
    sweep,
    friction,
    height,
    drive = null,
  }: {
    config: ConfigStore;
    sweep: ForceSweepResult | null;
    friction: FrictionBudgetDto | null;
    height: HeightStackResultDto | null;
    drive?: DriveAnalysis | null;
  } = $props();

  let netUsableN = $derived.by(() => {
    if (!sweep || !friction) return null;
    return sweep.mean_thrust_n - friction.total_n;
  });

</script>

<div class="metrics space-y-4">
  <h3 class="text-sm font-semibold text-slate-200 border-b border-slate-700 pb-1">
    Live metrics
  </h3>

  <!-- Primary thrust metrics -->
  <div class="primary-metrics grid grid-cols-2 gap-2">
    <div>
      <div class="text-xs text-slate-400">Peak thrust</div>
      <div class="font-mono text-lg text-sky-300">{sweep ? sweep.peak_thrust_n.toFixed(3) : "—"} <span class="text-xs text-slate-500">N</span></div>
    </div>
    <div>
      <div class="text-xs text-slate-400">Mean thrust</div>
      <div class="font-mono text-lg text-emerald-300">{sweep ? sweep.mean_thrust_n.toFixed(3) : "—"} <span class="text-xs text-slate-500">N</span></div>
    </div>
    <div>
      <div class="text-xs text-slate-400">Minimum thrust</div>
      <div class="font-mono text-lg text-rose-300">{sweep ? sweep.min_thrust_n.toFixed(3) : "—"} <span class="text-xs text-slate-500">N</span></div>
    </div>
    <div>
      <div class="text-xs text-slate-400">Thrust ripple<HelpTag label="About thrust ripple" tip="Position-dependent force variation, not PWM current ripple." equation={String.raw`r_F = \frac{F_{\max} - F_{\min}}{|\overline{F}|}\times 100\%`} /></div>
      <div class="font-mono text-lg {rippleStatus(sweep?.ripple_pct) === 'ok' ? 'text-emerald-300' : rippleStatus(sweep?.ripple_pct) === 'warn' ? 'text-amber-300' : 'text-rose-300'}">
        {sweep ? sweep.ripple_pct.toFixed(1) : "—"} <span class="text-xs text-slate-500">%</span>
      </div>
    </div>
  </div>

  <div class="border-y border-slate-700 py-3">
    <div class="text-xs text-slate-300">Net usable thrust<HelpTag label="About net usable thrust" tip="Mean motor thrust after mechanical friction. A negative value cannot overcome the estimated friction." equation={String.raw`F_{\mathrm{net}} = \overline{F} - F_{\mathrm{friction}}`} /></div>
    {#if netUsableN !== null}
      <div class="mt-2 text-sm">
        <span class="font-mono {netUsableN > 0 ? 'text-emerald-300' : 'text-rose-400'}">{netUsableN.toFixed(3)} N</span>
      </div>
    {:else}
      <span class="text-xs text-slate-400">Waiting for simulation…</span>
    {/if}
  </div>

  <!-- Friction breakdown -->
  <details>
    <summary class="cursor-pointer text-xs text-slate-400">Friction breakdown</summary>
    {#if friction}
      <div class="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs font-mono">
        <span class="text-slate-300">Bearing: <span class="text-slate-100">{(friction.bearing_friction_n * 1000).toFixed(1)} mN</span></span>
        <span class="text-slate-300">Cable drag: <span class="text-slate-100">{(friction.cable_drag_n * 1000).toFixed(1)} mN</span></span>
        <span class="text-slate-300">Wiper: <span class="text-slate-100">{(friction.wiper_contact_n * 1000).toFixed(1)} mN</span></span>
        <span class="text-slate-300">Detent (cogging): <span class="text-slate-100">{(friction.cogging_n * 1000).toFixed(1)} mN</span></span>
        <span class="text-slate-300 col-span-2">Total: <span class="text-rose-300">{(friction.total_n * 1000).toFixed(1)} mN</span> · Min drive: <span class="text-amber-300">{(friction.minimum_drive_force_n * 1000).toFixed(1)} mN</span></span>
      </div>
    {:else}
      <div class="text-xs text-slate-500">Awaiting friction budget…</div>
    {/if}
  </details>

  <!-- Height stack -->
  <details>
    <summary class="cursor-pointer text-xs text-slate-400">Height stack</summary>
    {#if height}
      <div class="grid grid-cols-2 gap-x-3 gap-y-1 text-xs font-mono">
        <span class="text-slate-300">PCB: <span class="text-slate-100">{(height.pcb_thickness_m * 1000).toFixed(2)} mm</span></span>
        <span class="text-slate-300">Air gap: <span class="text-slate-100">{(height.air_gap_m * 1000).toFixed(2)} mm</span></span>
        <span class="text-slate-300">Magnet: <span class="text-slate-100">{(height.magnet_height_m * 1000).toFixed(2)} mm</span></span>
        <span class="text-slate-300 col-span-2">Total: <span class="text-emerald-300">{(height.total_height_m * 1000).toFixed(2)} mm</span></span>
      </div>
    {:else}
      <div class="text-xs text-slate-500">Awaiting height stack…</div>
    {/if}
  </details>

  <!-- Drive config echo -->
  <div class="text-xs text-slate-400">
    Selected simulation inputs: {commutationLabel(config.commutation)} · {config.phases} phase · {config.max_current_a.toFixed(2)} A phase amplitude · {config.supply_voltage_v.toFixed(1)} V bus.
    This is not the DC supply current.
  </div>
  {#if drive}
    <CurrentBudget analysis={drive} />
    <p class="text-xs text-slate-400">
      Calculated continuous phase-current ceiling: <span class="font-mono text-slate-200">{drive.max_continuous_current_a.toFixed(2)} A</span>,
      limited by {drive.limiting_factor}. Standstill estimate; see driver checks for PWM ripple and target-speed limits.
    </p>
  {/if}
</div>

<style>
  .metrics { container-type: inline-size; }
  @container (min-width: 680px) {
    .primary-metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  }
</style>
