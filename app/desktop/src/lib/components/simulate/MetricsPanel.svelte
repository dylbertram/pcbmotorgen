<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type {
    CommutationMode,
    ForceSweepResult,
    FrictionBudgetDto,
    HeightStackResultDto,
  } from "../../types";
  import { rippleStatus } from "../../format";

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
  }: {
    config: ConfigStore;
    sweep: ForceSweepResult | null;
    friction: FrictionBudgetDto | null;
    height: HeightStackResultDto | null;
  } = $props();

  let netUsableN = $derived.by(() => {
    if (!sweep || !friction) return null;
    return sweep.mean_thrust_n - friction.total_n;
  });

  // Stacked-bar fractions for the EM vs friction vs net chart.
  let barSegments = $derived.by(() => {
    if (!sweep || !friction) return null;
    const em = Math.max(sweep.mean_thrust_n, 0);
    const fr = friction.total_n;
    const net = Math.max(em - fr, 0);
    const total = em + fr + net;
    const pct = (v: number) => (total > 0 ? (v / total) * 100 : 0);
    return {
      em: { val: em, pct: pct(em) },
      fr: { val: fr, pct: pct(fr) },
      net: { val: net, pct: pct(net) },
    };
  });
</script>

<div class="space-y-4">
  <h3 class="text-sm font-semibold text-slate-200 border-b border-slate-700 pb-1">
    Live Metrics
  </h3>

  <!-- Primary thrust metrics -->
  <div class="grid grid-cols-2 gap-2">
    <div class="rounded-md bg-slate-800/60 border border-slate-700 px-3 py-2">
      <div class="text-xs text-slate-400">Peak Thrust</div>
      <div class="font-mono text-lg text-sky-300">{sweep ? sweep.peak_thrust_n.toFixed(3) : "—"} <span class="text-xs text-slate-500">N</span></div>
    </div>
    <div class="rounded-md bg-slate-800/60 border border-slate-700 px-3 py-2">
      <div class="text-xs text-slate-400">Mean Thrust</div>
      <div class="font-mono text-lg text-emerald-300">{sweep ? sweep.mean_thrust_n.toFixed(3) : "—"} <span class="text-xs text-slate-500">N</span></div>
    </div>
    <div class="rounded-md bg-slate-800/60 border border-slate-700 px-3 py-2">
      <div class="text-xs text-slate-400">Min Thrust</div>
      <div class="font-mono text-lg text-rose-300">{sweep ? sweep.min_thrust_n.toFixed(3) : "—"} <span class="text-xs text-slate-500">N</span></div>
    </div>
    <div class="rounded-md bg-slate-800/60 border border-slate-700 px-3 py-2">
      <div class="text-xs text-slate-400">Thrust Ripple</div>
      <div class="font-mono text-lg {rippleStatus(sweep?.ripple_pct) === 'ok' ? 'text-emerald-300' : rippleStatus(sweep?.ripple_pct) === 'warn' ? 'text-amber-300' : 'text-rose-300'}">
        {sweep ? sweep.ripple_pct.toFixed(1) : "—"} <span class="text-xs text-slate-500">%</span>
      </div>
    </div>
  </div>

  <!-- Stacked bar: electromagnetic vs friction vs net usable -->
  <div class="rounded-md bg-slate-800/60 border border-slate-700 px-3 py-3">
    <div class="text-xs text-slate-400 mb-2">Net Usable Thrust Margin (F_em − F_friction)</div>
    {#if barSegments}
      <div class="flex h-5 w-full rounded overflow-hidden border border-slate-700">
        <div class="bg-emerald-500" style:width="{barSegments.em.pct}%"></div>
        <div class="bg-rose-500" style:width="{barSegments.fr.pct}%"></div>
        <div class="bg-sky-500" style:width="{barSegments.net.pct}%"></div>
      </div>
      <div class="flex justify-between text-xs mt-1.5">
        <span class="text-emerald-400">EM {barSegments.em.val.toFixed(3)} N</span>
        <span class="text-rose-400">Friction {barSegments.fr.val.toFixed(3)} N</span>
        <span class="text-sky-300">Net {barSegments.net.val.toFixed(3)} N</span>
      </div>
    {:else}
      <div class="text-xs text-slate-500">Awaiting thrust + friction computation…</div>
    {/if}
    {#if netUsableN !== null}
      <div class="mt-2 text-sm">
        Net usable margin:
        <span class="font-mono {netUsableN > 0 ? 'text-emerald-300' : 'text-rose-400'}">{netUsableN.toFixed(3)} N</span>
      </div>
    {/if}
  </div>

  <!-- Friction breakdown -->
  <div class="rounded-md bg-slate-800/60 border border-slate-700 px-3 py-2">
    <div class="text-xs text-slate-400 mb-1">Friction Breakdown</div>
    {#if friction}
      <div class="grid grid-cols-2 gap-x-3 gap-y-1 text-xs font-mono">
        <span class="text-slate-300">Bearing: <span class="text-slate-100">{(friction.bearing_friction_n * 1000).toFixed(1)} mN</span></span>
        <span class="text-slate-300">Cable drag: <span class="text-slate-100">{(friction.cable_drag_n * 1000).toFixed(1)} mN</span></span>
        <span class="text-slate-300">Wiper: <span class="text-slate-100">{(friction.wiper_contact_n * 1000).toFixed(1)} mN</span></span>
        <span class="text-slate-300">Detent (cogging): <span class="text-slate-100">{(friction.cogging_n * 1000).toFixed(1)} mN</span></span>
        <span class="text-slate-300 col-span-2">Total: <span class="text-rose-300">{(friction.total_n * 1000).toFixed(1)} mN</span> · Min drive: <span class="text-amber-300">{(friction.minimum_drive_force_n * 1000).toFixed(1)} mN</span></span>
      </div>
    {:else}
      <div class="text-xs text-slate-500">Awaiting friction budget…</div>
    {/if}
  </div>

  <!-- Height stack -->
  <div class="rounded-md bg-slate-800/60 border border-slate-700 px-3 py-2">
    <div class="text-xs text-slate-400 mb-1">Height Stack</div>
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
  </div>

  <!-- Drive config echo -->
  <div class="rounded-md bg-slate-800/40 border border-slate-700 px-3 py-2 text-xs text-slate-400">
    Drive: {commutationLabel(config.commutation)} · {config.phases} phase · {config.max_current_a.toFixed(2)} A @ {config.supply_voltage_v.toFixed(1)} V
  </div>
</div>
