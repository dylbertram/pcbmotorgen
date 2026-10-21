<script lang="ts">
  import { onMount, onDestroy, untrack } from "svelte";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { CadGeometry, LinearMotorConfig, DriveSettings } from "../../types";
  import type { DcCapability, DcStudy } from "../../types/dcCoupling";
  import { dcCouplingCapability, startDcCoupling, dcCouplingStatus, cancelDcCoupling } from "../../ipc/dcJobs";
  import { DcJobController, type DcViewState } from "../../dcJobController";

  let { config, cadGeometry = null, active }: { config: ConfigStore; cadGeometry?: CadGeometry | null; active: boolean } = $props();
  let capability = $state<DcCapability>({ available: false, reason: "Checking the desktop DC worker…" });
  let view = $state<DcViewState>({ phase: "idle", job: null, error: null });
  let declaration = $state("");
  let current = $state(0);
  let offset = $state(0);
  let acknowledged = $state(false);
  let inputError = $state<string | null>(null);
  const busy = $derived(["starting", "running", "cancelling"].includes(view.phase));
  const force = $derived(view.phase === "completed" ? view.job?.result?.pm_array_force_n : null);
  let destroyed = false;
  let submitted: { config: LinearMotorConfig; drive: DriveSettings; cad: CadGeometry | null; study: DcStudy } | null = null;
  const controller = new DcJobController({
    start: () => {
      const request = submitted!;
      return startDcCoupling(request.config, request.drive, request.cad, request.study);
    },
    poll: dcCouplingStatus,
    cancel: cancelDcCoupling,
  }, next => { if (!destroyed) view = next; });

  // Every physical input participates in invalidation, including edits outside
  // this panel. Never reuse a force for another design or hidden tab.
  $effect.pre(() => {
    void JSON.stringify(config.toIpc());void JSON.stringify(config.drive);void JSON.stringify(cadGeometry);
    void declaration;void current;void offset;void acknowledged;void active;
    untrack(() => { inputError = null;void controller.invalidate(); });
  });
  $effect(() => {
    if (!active) return;
    let cancelled = false;
    void dcCouplingCapability().then(next => { if (!cancelled) capability = next; })
      .catch(error => { if (!cancelled) capability = { available: false, reason: String(error) }; });
    return () => { cancelled = true; };
  });
  onMount(() => {
    const timer = setInterval(() => { void controller.poll(); }, 300);
    return () => clearInterval(timer);
  });
  onDestroy(() => { destroyed = true;void controller.invalidate(); });

  async function calculate() {
    inputError = null;
    try {
      const explicit = JSON.parse(declaration);
      if (!explicit || typeof explicit !== "object" || Array.isArray(explicit)
        || Object.keys(explicit).sort().join(",") !== "material_model,return_geometry"
        || !explicit.material_model || typeof explicit.material_model !== "object" || Array.isArray(explicit.material_model)
        || !explicit.return_geometry || typeof explicit.return_geometry !== "object" || Array.isArray(explicit.return_geometry)) {
        throw new Error("Provide exactly material_model and return_geometry objects. Do not include archived forces or winding snapshots.");
      }
      const study: DcStudy = { request_id: crypto.randomUUID(), material_model: explicit.material_model,
        return_geometry: explicit.return_geometry, current_a: current, pm_offset_x_m: offset,
        placement_acknowledged: acknowledged };
      submitted = { config: $state.snapshot(config.toIpc()), drive: $state.snapshot(config.drive),
        cad: $state.snapshot(cadGeometry), study };
      await controller.start(study.request_id);
    } catch (error) {
      await controller.invalidate();inputError = String(error);
    }
  }
</script>

<section aria-label="Experimental static DC coupling" class="max-w-4xl space-y-3 text-xs text-slate-300">
  <div class="space-y-1">
    <h3 class="font-semibold text-slate-100">Static DC winding–magnet–shield coupling</h3>
    <p class="max-w-3xl leading-relaxed text-amber-200">Restricted to the recorded, verified geometry and sampled current/pose states. Other designs are rejected, not approximated. The reversible ferrite law is provisional. No temperature, hardware rating, reversal cycle or differential inductance prediction.</p>
  </div>
  {#if !capability.available}
    <p role="status" class="text-slate-400">{capability.reason}</p>
  {/if}
  <div class="grid gap-3 sm:grid-cols-2">
    <label class="flex items-center justify-between gap-2">Loop current (A)
      <select bind:value={current} class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-slate-100">
        {#each [-0.5, -0.1, 0, 0.1, 0.5] as value (value)}<option {value}>{value}</option>{/each}
      </select>
    </label>
    <label class="flex items-center justify-between gap-2">PM lateral offset (µm)
      <select bind:value={offset} class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-slate-100">
        {#each [-0.0001, 0, 0.0001] as value (value)}<option {value}>{value * 1e6}</option>{/each}
      </select>
    </label>
  </div>
  <label class="block space-y-1">
    <span>Explicit material placement and finite return (JSON, SI units)</span>
    <textarea bind:value={declaration} rows="5" spellcheck="false" placeholder={'{"material_model": {...}, "return_geometry": {...}}'}
      class="w-full rounded border border-slate-600 bg-slate-950 p-2 font-mono text-xs text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400"></textarea>
  </label>
  <p class="text-slate-400">Use the full physical model and declared return from an approved study. Copper is rebuilt from the active design, not this JSON. No automatic clearance correction or invented return. New geometry requires separate qualification.</p>
  <label class="flex items-start gap-2">
    <input type="checkbox" bind:checked={acknowledged} class="mt-0.5" />
    <span>I acknowledge this explicit physical material placement and finite return. This does not modify the saved design or approve corrections for other designs.</span>
  </label>
  <div class="flex flex-wrap items-center gap-3">
    <button type="button" disabled={!capability.available || !acknowledged || !declaration.trim() || busy || !active} onclick={calculate}
      class="rounded border border-emerald-600 px-3 py-1.5 text-emerald-200 hover:bg-emerald-950 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Calculate static DC force</button>
    {#if busy}
      <button type="button" onclick={() => { void controller.cancel(); }} disabled={view.phase === "cancelling"}
        class="rounded border border-slate-600 px-3 py-1.5 hover:bg-slate-800 disabled:opacity-40">Cancel DC job</button>
      <p role="status" class="text-slate-400">{view.phase === "cancelling" ? "Waiting for the desktop worker to stop. No force is displayed." : "Calculating fresh fields. The recorded-case solve takes about 90–100 s; the whole job is capped at 360 s."}</p>
    {/if}
  </div>
  {#if inputError || view.error}
    <p role="alert" class="break-words text-amber-200">DC coupling unavailable: {inputError ?? view.error}</p>
  {:else if view.phase === "cancelled"}
    <p role="status" class="text-slate-400">DC request cancelled. No force is displayed.</p>
  {/if}
  {#if force}
    <dl aria-label="Fresh static DC force results" class="grid grid-cols-2 gap-x-4 gap-y-1 border-t border-slate-700 pt-3">
      {#each ["X", "Y", "Z"] as axis, index (axis)}
        <dt>PM-array force {axis}</dt><dd class="font-mono text-emerald-200">{force[index].toPrecision(6)} N</dd>
      {/each}
    </dl>
    <p class="text-slate-400">Force-vector norm gates: 2% refinement, 5% independent agreement, 1e-8 N floor. Componentwise relative accuracy and interpolation are not qualified.</p>
    <p class="break-all text-slate-400">Request SHA256: {view.job?.request_sha256}</p>
    <p class="break-all text-slate-400">Evidence: {view.job?.evidence_directory}</p>
  {/if}
</section>
