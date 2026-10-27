<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { PeriodicStaticReference } from "../../types/periodicReference";
  import { periodicBackplaneReference } from "../../ipc/physics";

  let { config }: { config: ConfigStore } = $props();
  let input = $derived(config.toIpc());
  let inputKey = $derived(JSON.stringify(input));
  let pending = $state(false);
  let result = $state.raw<{ key: string; data: PeriodicStaticReference } | null>(null);
  let failure = $state.raw<{ key: string; message: string } | null>(null);
  let current = $derived(result?.key === inputKey ? result.data : null);
  let lastRun = $derived(current?.runs.at(-1));
  let error = $derived(failure?.key === inputKey ? failure.message : null);
  let stale = $derived(result !== null && result.key !== inputKey);

  async function runReference() {
    if (pending) return;
    const key = inputKey;
    // A plain snapshot prevents later edits from changing the in-flight input.
    const snapshot = JSON.parse(key);
    pending = true;
    failure = null;
    result = null;
    try {
      const data = await periodicBackplaneReference(snapshot);
      result = { key, data };
    } catch (cause) {
      failure = { key, message: cause instanceof Error ? cause.message : String(cause) };
    } finally {
      pending = false;
    }
  }
</script>

<section class="mt-3 space-y-2 border-t border-slate-700 pt-3" aria-label="Periodic static reference">
  <h3 class="text-xs font-medium text-slate-200">Periodic static reference</h3>
  <p class="text-[11px] leading-relaxed text-slate-400">
    Compare thickness and saturation with a coupled vector-field model. Supports one magnetic
    layer and a nonmagnetic housing. Runs only on request; the fast preview stays unchanged.
  </p>
  <button
    type="button"
    class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-slate-200 hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400 disabled:cursor-wait disabled:opacity-50"
    disabled={pending}
    onclick={runReference}
  >{pending ? "Checking periodic reference…" : "Run periodic reference"}</button>
  <div aria-live="polite" class="space-y-2 text-[11px] leading-relaxed">
    {#if error}
      <p class="text-amber-300">{error}</p>
    {:else if stale}
      <p class="text-amber-300">Settings changed. Run the reference again for current values.</p>
    {:else if current && lastRun}
      <dl class="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-slate-300">
        <dt>PCB-top field ratio at magnet centre</dt>
        <dd class="font-mono">{lastRun.field_ratio_at_pm_centre_pcb_top.toFixed(4)}×</dd>
        <dt>Periodic pressure over magnet width</dt>
        <dd class="font-mono">{(lastRun.mean_pressure_over_magnet_width_pa / 1000).toFixed(3)} kPa</dd>
        <dt>Sampled peak B in the layer</dt>
        <dd class="font-mono">{lastRun.quadrature_sampled_peak_b_t.toFixed(3)} T</dd>
        <dt>Sampled layer fraction above the knee</dt>
        <dd class="font-mono">{(lastRun.quadrature_saturated_fraction * 100).toFixed(1)}%</dd>
        <dt>Isolated-sheet DC factors, two alignments</dt>
        <dd class="font-mono">{lastRun.isolated_sheet_dc_factors_per_alignment[0].toFixed(4)}× / {lastRun.isolated_sheet_dc_factors_per_alignment[1].toFixed(4)}×</dd>
        <dt>Largest static refinement change</dt>
        <dd class="font-mono">{(100 * Math.max(current.max_field_refinement_change, current.max_pressure_refinement_change)).toFixed(2)}%</dd>
      </dl>
      <p class="text-slate-400">
        Above the knee, B can exceed the saturation polarization through the μ₀H term.
        The peak is sampled, not a resolved sharp-edge maximum.
      </p>
      <p class="text-slate-400">
        DC factors compare two isolated 20 μm sinusoidal sheets at the PCB faces, not your
        winding. They are not a minimum inductance across travel or a safe PWM ripple limit.
      </p>
      <p class="text-amber-300">
        Infinite periodic array and cross-depth. This is not finite-motor force or a bearing load.
        Your winding's AC impedance, housing eddy currents and PWM are not solved.
      </p>
      <details class="text-slate-400">
        <summary class="cursor-pointer">Resolution and model limits</summary>
        <p class="mt-1">Reference completed in {current.elapsed_seconds.toFixed(1)} s.</p>
        <p class="mt-1">Largest DC factor refinement change: {current.max_dc_factor_absolute_refinement_change.toPrecision(3)}.</p>
        <ul class="mt-1 list-disc space-y-1 pl-4">
          {#each current.runs as run (run.angular_samples + ":" + run.odd_modes + ":" + run.depth_cells)}
            <li>{run.depth_cells} depth cells, {run.odd_modes} odd modes, {run.angular_samples} angles;
              residual {run.relative_gradient_residual.toExponential(1)}</li>
          {/each}
          {#each current.warnings as warning (warning)}
            <li>{warning}</li>
          {/each}
        </ul>
      </details>
    {/if}
  </div>
</section>
