<script lang="ts">
  import { onDestroy, onMount, untrack } from "svelte";
  import type { CadGeometry } from "../../types";
  import type { VisualizationInput } from "../../types/simulationVisualization";
  import type { DcCapability, DcStudy, DcWindingFieldResult, WindingFieldSampling } from "../../types/dcCoupling";
  import { dcCouplingCapability, startDcWindingField, dcCouplingStatus, cancelDcCoupling } from "../../ipc/dcJobs";
  import { DcJobController, type DcViewState } from "../../dcJobController";

  let { input, geometry, active, onResult }: { input: VisualizationInput; geometry: CadGeometry; active: boolean; onResult: (value: DcWindingFieldResult | null) => void } = $props();
  let capability = $state<DcCapability>({ available: false, reason: "Checking qualified finite-copper sources…" });
  let selected = $state("");
  let current = $state(.1);
  let acknowledged = $state(false);
  let view = $state<DcViewState>({ phase: "idle", job: null, error: null });
  let destroyed = false;
  let submitted: { input: VisualizationInput; study: DcStudy; sampling: WindingFieldSampling } | null = null;
  const entry = $derived(capability.qualified_cases?.find(value => value.case_id === selected) ?? null);
  const busy = $derived(["starting", "running", "cancelling"].includes(view.phase));
  const controller = new DcJobController({
    start: () => { const s = submitted!; return startDcWindingField(s.input.config, s.input.drive, s.input.cadGeometry, s.study, s.sampling); },
    poll: dcCouplingStatus, cancel: cancelDcCoupling,
  }, next => {
    if (destroyed) return;
    view = next;
    onResult(next.phase === "completed" ? next.job?.winding_field ?? null : null);
  });
  $effect.pre(() => {
    void JSON.stringify(input); void JSON.stringify(geometry); void selected;
    untrack(() => { acknowledged = false; });
  });
  $effect.pre(() => {
    void JSON.stringify(input); void JSON.stringify(geometry); void active; void selected; void current; void acknowledged;
    untrack(() => { void controller.invalidate(); });
  });
  $effect(() => {
    if (!active) return;
    let cancelled = false;
    void dcCouplingCapability().then(value => { if (!cancelled) capability = value; })
      .catch(error => { if (!cancelled) capability = { available: false, reason: String(error) }; });
    return () => { cancelled = true; };
  });
  onMount(() => { const timer = setInterval(() => { void controller.poll(); }, 300); return () => clearInterval(timer); });
  onDestroy(() => { destroyed = true; onResult(null); void controller.invalidate(); });

  async function sample() {
    if (!entry || !acknowledged || !active || busy) return;
    const positions = [...geometry.routing.segments.flatMap(s => [s.start, s.end]), ...geometry.routing.curves.flatMap(c => [c.start, c.mid, c.end])];
    if (!positions.length) return;
    const x = positions.map(p => p.x * .001), y = positions.map(p => p.y * .001);
    const sampling: WindingFieldSampling = { bounds_m: [[Math.min(...x) - .001, Math.max(...x) + .001], [Math.min(...y) - .001, Math.max(...y) + .001],
      [Math.min(...geometry.layer_z_mm) * .001 - .003, Math.max(...geometry.layer_z_mm) * .001 + .003]], counts: [8, 3, 4] };
    const study: DcStudy = { request_id: crypto.randomUUID(), ...$state.snapshot(entry.declaration), current_a: current, pm_offset_x_m: 0, placement_acknowledged: acknowledged };
    submitted = { input: $state.snapshot(input), study, sampling };
    await controller.start(study.request_id);
  }
</script>

<div class="basis-full space-y-2 border-t border-slate-700 pt-2" aria-label="Qualified coil field controls">
  <p>Coils' own field from an audited finite-copper DC source, including its declared return. No magnet or material-response field. The active design must match exactly.</p>
  {#if !capability.available || capability.winding_field_available === false}
    <p role="status">Coil field unavailable: {capability.reason ?? "Install the qualified winding-field worker on this host."} No magnet field or wire substitute is shown.</p>
  {:else}
    <label class="flex flex-wrap items-center gap-2">Audited coil source
      <select aria-label="Audited coil source" bind:value={selected} disabled={busy} class="min-w-0 max-w-full rounded border border-slate-600 bg-slate-800 p-1">
        <option value="">Choose an exact qualified source</option>
        {#each capability.qualified_cases ?? [] as value (value.case_id)}<option value={value.case_id}>{value.label}</option>{/each}
      </select>
    </label>
    <label class="flex items-center gap-2">DC loop current (A)
      <select aria-label="Coil DC loop current" bind:value={current} class="rounded border border-slate-600 bg-slate-800 p-1">
        {#each [-.5, -.1, 0, .1, .5] as value (value)}<option {value}>{value}</option>{/each}
      </select>
    </label>
    {#if entry}
      <details><summary>Audited placement and finite return</summary><pre class="max-h-32 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(entry.declaration, null, 2)}</pre></details>
      <label class="flex items-start gap-2"><input type="checkbox" bind:checked={acknowledged} /><span>I acknowledge this audited placement and finite return for this exact design. No geometry is moved or repaired.</span></label>
    {/if}
    <p>Audited DC drive-loop configuration only, not independent AC phase excitation. 96 exterior observations, direct finite-cell integration, 180 s whole-job and 4 GiB memory limits. New display points are not newly qualified field-refinement results.</p>
    <button type="button" disabled={!entry || !acknowledged || busy || !active} onclick={sample} class="rounded border border-emerald-600 px-2 py-1 disabled:opacity-40">Sample coil B-field</button>
    {#if busy}<button type="button" onclick={() => { void controller.cancel(); }} class="rounded border border-slate-600 px-2 py-1">Cancel coil field</button><p role="status">Sampling the finite-copper current source. Previous coil field cleared.</p>{/if}
  {/if}
  {#if view.error}<p role="alert" class="text-amber-200">Coil field unavailable: {view.error}</p>{/if}
  {#if view.phase === "cancelled"}<p role="status">Coil field cancelled. No old winding field is displayed.</p>{/if}
  {#if view.phase === "completed" && view.job?.winding_field}<p>{view.job.winding_field.qualified_case.label} · {view.job.winding_field.loop_current_a} A DC loop. {Object.entries(view.job.winding_field.phase_currents_a).map(([net, amps]) => `${net}: ${amps} A`).join(", ")}</p>{/if}
</div>
