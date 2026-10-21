<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { HousingMotionAnalysis } from "../../types/drive";
  import type { CadGeometry } from "../../types";
  import NumberField from "../ui/NumberField.svelte";
  import { validateBackplaneInput } from "../../validation";
  import { analyzeHousingMotion } from "../../ipc";

  let { config, cadGeometry = null }: { config: ConfigStore; cadGeometry?: CadGeometry | null } = $props();
  let result = $state<HousingMotionAnalysis | null>(null);
  let error = $state<string | null>(null);
  let pending = $state(false);
  const enabled = $derived(config.drive.housing_motion != null);
  const inputError = $derived(validateBackplaneInput(config.backplane).find((finding) => finding.level === "error")?.message ??
    (enabled && (!Number.isFinite(config.drive.housing_motion?.duration_s) || (config.drive.housing_motion?.duration_s ?? 0) <= 0)
      ? "Steady exposure must have a positive finite duration." : null));

  // An independent request lifecycle prevents unrelated driver errors and
  // late responses for previous geometry from replacing housing results.
  $effect(() => {
    const profile = config.drive.housing_motion;
    void JSON.stringify(config.toIpc());
    void JSON.stringify(cadGeometry);
    const configSnapshot = $state.snapshot(config.toIpc());
    const geometrySnapshot = $state.snapshot(cadGeometry);
    const speed = config.drive.target_speed_m_s;
    const duration_s = profile?.duration_s;
    const invalid = inputError;
    let cancelled = false;
    result = null; error = null; pending = false;
    if (!profile || invalid) return;
    pending = true;
    const timer = setTimeout(async () => {
      try {
        const next = await analyzeHousingMotion(configSnapshot, { duration_s: duration_s! }, speed, geometrySnapshot);
        if (!cancelled) { result = next; pending = false; }
      } catch (cause) {
        if (!cancelled) { error = cause instanceof Error ? cause.message : String(cause); pending = false; }
      }
    }, 120);
    return () => { cancelled = true; clearTimeout(timer); };
  });
  function enable(value: boolean) {
    config.drive = { ...config.drive, housing_motion: value ? { duration_s: 0.1 } : null };
  }
  function duration(value: number) {
    config.drive = { ...config.drive, housing_motion: { duration_s: value } };
  }
</script>

<section class="mt-3 space-y-2 border-t border-slate-700/70 pt-2.5" aria-label="Experimental housing motion">
  <label class="flex items-center gap-2 text-xs text-slate-200">
    <input type="checkbox" checked={enabled} onchange={(event) => enable(event.currentTarget.checked)} />
    Motion-induced housing drag and heating (experimental)
  </label>
  {#if enabled}
    <p class="text-[11px] leading-relaxed text-amber-200">
      Planar steady-travel screening with magnetic feedback, not finite 3D housing or temperature prediction.
      Starts, stops, slots and finite ends are not resolved. No hardware rating.
    </p>
    <label class="flex items-center justify-between gap-2 text-xs text-slate-300">
      Steady exposure (s)
      <NumberField value={config.drive.housing_motion?.duration_s ?? 0.1} min={0.000001} step={0.01}
        ariaLabel="Housing steady exposure duration (s)" class="w-24 px-2 py-1 text-xs font-mono text-emerald-200" onCommit={duration} />
    </label>
    <label class="flex items-center justify-between gap-2 text-xs text-slate-300">
      Motion speed (m/s)
      <NumberField value={config.drive.target_speed_m_s} min={0} step={0.1}
        ariaLabel="Housing motion speed (m/s)" class="w-24 px-2 py-1 text-xs font-mono text-emerald-200"
        onCommit={(value) => { config.drive = { ...config.drive, target_speed_m_s: value }; }} />
    </label>
    {#if inputError || error}
      <p role="alert" class="text-[11px] text-amber-200">Housing motion estimate unavailable: {inputError ?? error}</p>
    {:else if pending}
      <p role="status" class="text-[11px] text-slate-400">Calculating current housing motion settings. No previous estimate is reused.</p>
    {:else if result?.status === "experimental"}
      <dl class="grid grid-cols-2 gap-x-3 gap-y-1 text-xs" aria-label="Experimental housing motion results">
        <dt class="text-slate-400">Housing-equivalent drag</dt><dd class="font-mono text-slate-200">{result.estimate.housing_drag_n.toPrecision(3)} N</dd>
        <dt class="text-slate-400">Total stack drag</dt><dd class="font-mono text-slate-200">{result.estimate.total_stack_drag_n.toPrecision(3)} N</dd>
        <dt class="text-slate-400">Housing Joule heat</dt><dd class="font-mono text-slate-200">{result.estimate.housing_joule_power_w.toPrecision(3)} W</dd>
        <dt class="text-slate-400">Housing exposure energy</dt><dd class="font-mono text-slate-200">{result.estimate.housing_energy_j.toPrecision(3)} J</dd>
        <dt class="text-slate-400">Total stack Joule heat</dt><dd class="font-mono text-slate-200">{result.estimate.total_stack_joule_power_w.toPrecision(3)} W</dd>
        <dt class="text-slate-400">Equivalent travel</dt><dd class="font-mono text-slate-200">{(result.estimate.equivalent_travel_m * 1e3).toPrecision(3)} mm</dd>
      </dl>
      <ul class="list-disc space-y-1 pl-4 text-[11px] text-amber-200">
        {#each result.estimate.warnings as warning (warning)}<li>{warning}</li>{/each}
      </ul>
    {:else if result?.status === "unavailable"}
      <p role="alert" class="text-[11px] text-amber-200">Housing motion estimate unavailable: {result.reason}</p>
    {:else}
      <p role="status" class="text-[11px] text-slate-400">Choose a supported housing and motion profile to calculate. No previous estimate is reused.</p>
    {/if}
  {/if}
</section>
