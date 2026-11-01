<script lang="ts">
  import { onMount, onDestroy, untrack } from "svelte";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { CadGeometry, LinearMotorConfig, DriveSettings } from "../../types";
  import type { DcApplicability, DcCapability, DcQualifiedCase, DcStudy } from "../../types/dcCoupling";
  import { dcCouplingCapability, inspectDcCoupling, startDcCoupling, startDcPreparation, dcCouplingStatus, cancelDcCoupling } from "../../ipc/dcJobs";
  import { DcJobController, type DcViewState } from "../../dcJobController";

  let { config, cadGeometry = null, active }: { config: ConfigStore; cadGeometry?: CadGeometry | null; active: boolean } = $props();
  let capability = $state<DcCapability>({ available: false, reason: "Checking the desktop DC worker…" });
  let view = $state<DcViewState>({ phase: "idle", job: null, error: null });
  let declaration = $state("");
  let current = $state(0);
  let offset = $state(0);
  let acknowledged = $state(false);
  let preparationAcknowledged = $state(false);
  let operation = $state<"force" | "preparation">("force");
  let inputError = $state<string | null>(null);
  let applicability = $state<DcApplicability | null>(null);
  let inspecting = $state(false);
  let inspectionEpoch = 0;
  const busy = $derived(["starting", "running", "cancelling"].includes(view.phase));
  const force = $derived(view.phase === "completed" ? view.job?.result?.pm_array_force_n : null);
  const preparationStages = { geometry: "Exact copper and material separation", source: "Fresh 1 V current solve",
    active: "Active winding sections", passive: "Passive and stub sections", return: "Finite return sections",
    independent: "Independent current reference", rt0: "Exact finite-current source export" };
  let destroyed = false;
  let submitted: { config: LinearMotorConfig; drive: DriveSettings; cad: CadGeometry | null; study: DcStudy; operation: "force" | "preparation" } | null = null;
  const controller = new DcJobController({
    start: () => {
      const request = submitted!;
      return request.operation === "preparation" ? startDcPreparation(request.config, request.drive, request.cad, request.study, 14400)
        : startDcCoupling(request.config, request.drive, request.cad, request.study);
    },
    poll: dcCouplingStatus,
    cancel: cancelDcCoupling,
  }, next => { if (!destroyed) view = next; });

  // Every physical input participates in invalidation, including edits outside
  // this panel. Never reuse a force for another design or hidden tab.
  $effect.pre(() => {
    void JSON.stringify(config.toIpc());void JSON.stringify(config.drive);void JSON.stringify(cadGeometry);
    void declaration;void current;void offset;void acknowledged;void active;
    untrack(() => { inputError = null;applicability = null;preparationAcknowledged = false;inspectionEpoch++;inspecting = false;void controller.invalidate(); });
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
  onDestroy(() => { destroyed = true;inspectionEpoch++;void controller.invalidate(); });

  // Fills only the audited explicit placement/return; acknowledgement stays a
  // separate user action and the worker still checks the rebuilt copper.
  function useDeclaration(entry: DcQualifiedCase) {
    declaration = JSON.stringify(entry.declaration, null, 2);
    acknowledged = false;
  }

  function readStudy(): DcStudy {
    const explicit = JSON.parse(declaration);
    if (!explicit || typeof explicit !== "object" || Array.isArray(explicit)
      || Object.keys(explicit).sort().join(",") !== "material_model,return_geometry"
      || !explicit.material_model || typeof explicit.material_model !== "object" || Array.isArray(explicit.material_model)
      || !explicit.return_geometry || typeof explicit.return_geometry !== "object" || Array.isArray(explicit.return_geometry)) {
      throw new Error("Provide exactly material_model and return_geometry objects. Do not include archived forces or winding snapshots.");
    }
    return { request_id: crypto.randomUUID(), material_model: explicit.material_model,
      return_geometry: explicit.return_geometry, current_a: current, pm_offset_x_m: offset,
      placement_acknowledged: acknowledged };
  }

  async function inspectDesign() {
    inputError = null;applicability = null;
    const epoch = ++inspectionEpoch;
    inspecting = true;
    try {
      await controller.invalidate();
      if (destroyed || epoch !== inspectionEpoch) return;
      const study = readStudy();
      const next = await inspectDcCoupling($state.snapshot(config.toIpc()), $state.snapshot(config.drive), $state.snapshot(cadGeometry), study);
      if (destroyed || epoch !== inspectionEpoch) return;
      if (next.schema !== "finite-dc-applicability-v1" || next.request_id !== study.request_id) {
        throw new Error("The applicability response belongs to a different request. Check this design again.");
      }
      applicability = next;
    } catch (error) {
      if (!destroyed && epoch === inspectionEpoch) inputError = String(error);
    } finally {
      if (!destroyed && epoch === inspectionEpoch) inspecting = false;
    }
  }

  async function calculate(nextOperation: "force" | "preparation" = "force") {
    inputError = null;
    try {
      if (nextOperation === "preparation" && (!preparationAcknowledged || applicability?.state !== "preparation-required")) {
        throw new Error("Check this design and explicitly confirm the separate preparation budget first.");
      }
      operation = nextOperation;
      const study = readStudy();
      submitted = { config: $state.snapshot(config.toIpc()), drive: $state.snapshot(config.drive),
        cad: $state.snapshot(cadGeometry), study, operation: nextOperation };
      await controller.start(study.request_id);
    } catch (error) {
      await controller.invalidate();inputError = String(error);
    }
  }
</script>

<section aria-label="Audited DC force at one pose" class="max-w-4xl space-y-3 text-xs text-slate-300">
  <div class="space-y-1">
    <h3 class="font-semibold text-slate-100">DC force at one fixed magnet position</h3>
    <p class="max-w-3xl leading-relaxed">Calculates the force on the magnet array at one DC loop current and one lateral offset, including the declared magnetic materials. It is not a holding-force curve over travel. Use "Thrust vs. position" for the general routed-geometry force sweep. That sweep uses its configured commutation and does not calculate closed-loop holding stiffness.</p>
    <p class="max-w-3xl leading-relaxed text-amber-200">Restricted to designs individually qualified on this host and their sampled current/pose states. Any other design is rejected as needing qualification, not approximated. The reversible ferrite law is provisional. No temperature, hardware rating, reversal cycle or differential inductance prediction.</p>
  </div>
  {#if !capability.available}
    <p role="status" class="text-slate-400">{capability.reason}</p>
  {:else if capability.qualified_cases?.length}
    <div class="space-y-1">
      <p class="text-slate-400">Qualified designs on this host. The active design must match one exactly; nothing is matched approximately.</p>
      <ul aria-label="Qualified DC designs" class="space-y-1">
        {#each capability.qualified_cases as entry (entry.case_id)}
          <li class="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-700 px-2 py-1">
            <span class="text-slate-200">{entry.label}</span>
            <button type="button" onclick={() => useDeclaration(entry)} disabled={busy || inspecting}
              class="rounded border border-slate-600 px-2 py-0.5 hover:bg-slate-800 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Use audited placement</button>
          </li>
        {/each}
      </ul>
    </div>
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
   <p class="text-slate-400">Provide the full explicit physical model and finite return. Copper is rebuilt from the active design, not this JSON. No automatic clearance correction or invented return. Source preparation alone does not qualify a force; unlisted designs still need complete refinement and magnetic qualification.</p>
  <label class="flex items-start gap-2">
    <input type="checkbox" bind:checked={acknowledged} class="mt-0.5" />
    <span>I acknowledge this explicit physical material placement and finite return. This does not modify the saved design or approve corrections for other designs.</span>
  </label>
  <div class="flex flex-wrap items-center gap-3">
    <button type="button" disabled={(!capability.available && !capability.preparation_available) || !acknowledged || !declaration.trim() || busy || inspecting || !active} onclick={inspectDesign}
      class="rounded border border-slate-600 px-3 py-1.5 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Check this design</button>
    <button type="button" disabled={!capability.available || !acknowledged || !declaration.trim() || busy || inspecting || !active || (applicability !== null && applicability.state !== "qualified")} onclick={() => calculate()}
      class="rounded border border-emerald-600 px-3 py-1.5 text-emerald-200 hover:bg-emerald-950 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Calculate static DC force</button>
    {#if busy}
      <button type="button" onclick={() => { void controller.cancel(); }} disabled={view.phase === "cancelling"}
        class="rounded border border-slate-600 px-3 py-1.5 hover:bg-slate-800 disabled:opacity-40">Cancel DC job</button>
      <p role="status" class="text-slate-400">{view.phase === "cancelling" ? "Waiting for the desktop worker to stop. No force is displayed." : operation === "preparation"
        ? "Preparing actual copper and a fresh current source. This separate job can take hours, stops at 14,400 s and remains unqualified for force."
        : "Calculating fresh fields. Qualified-design solves take about 1–2 minutes; the whole job is capped at 360 s."}</p>
      {#if operation === "preparation" && view.job?.preparation_progress}
        <p role="status" class="text-slate-400">Current stage: {preparationStages[view.job.preparation_progress.stage]}. Stage hard limit: {view.job.preparation_progress.stage_timeout_s} s.</p>
      {/if}
    {/if}
  </div>
  {#if inspecting}
    <p role="status" class="text-slate-400">Checking the active copper, return and placement against verified evidence. No force is calculated.</p>
  {:else if applicability}
    <div aria-label="Active design DC applicability" class="space-y-1 rounded border border-slate-700 p-2">
      <p class="text-slate-200">{applicability.state === "qualified" ? "Qualified design" : applicability.state === "preparation-required" ? "Preparation required" : "Unsupported request"}</p>
      <p class="text-slate-400">{applicability.reason}</p>
      <p class="text-slate-400">Current source: {applicability.source_status === "qualified-exact-basis" ? "verified for this exact geometry" : "unqualified"}. Force scope: {applicability.force_status === "qualified-sampled-states" ? "sampled current and pose states only" : "unqualified"}.</p>
      {#if applicability.qualified_case}<p class="text-slate-400">{applicability.qualified_case.label}</p>{/if}
    </div>
  {/if}
  {#if applicability?.state === "preparation-required" && view.phase !== "prepared"}
    <div aria-label="Source preparation" class="space-y-2 rounded border border-slate-700 p-2">
      <p class="text-slate-200">Prepare the active design's current source</p>
      <p class="text-slate-400">Generated straight-trace designs only. CAD, fresh 1 V current, all local sections, independent current agreement and exact source export run serially. Estimated preparation: hours, with substantial design-dependent uncertainty. Hard limit: 4 hours and a sampled 13 GiB native-memory guard. Edits, tab departure and cancellation stop the owned job.</p>
      <p class="text-amber-200">This stage does not run the complete source refinements or magnetic qualification. It cannot register a case or return a force.</p>
      {#if capability.preparation_available}
        <label class="flex items-start gap-2"><input type="checkbox" bind:checked={preparationAcknowledged} disabled={busy} class="mt-0.5" /><span>I confirm the separate 14,400 s preparation budget. Source completion will still require refinement and force qualification.</span></label>
        <button type="button" disabled={!preparationAcknowledged || busy || inspecting || !active || cadGeometry !== null} onclick={() => calculate("preparation")}
          class="rounded border border-slate-600 px-3 py-1.5 hover:bg-slate-800 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Prepare current source</button>
      {:else}<p class="text-slate-400">{capability.preparation_reason ?? "A separately pinned source-preparation worker must be configured on this host."}</p>{/if}
    </div>
  {/if}
  {#if view.phase === "prepared" && view.job?.preparation}
    <div aria-label="Prepared unqualified current source" class="space-y-1 rounded border border-slate-700 p-2">
      <p class="text-slate-200">Current source prepared. Force remains unqualified.</p>
      <ul class="list-disc pl-4 text-slate-400">{#each view.job.preparation.remaining as remaining (remaining)}<li>{remaining}</li>{/each}</ul>
      <p class="break-all text-slate-400">Evidence: {view.job.evidence_directory}</p>
    </div>
  {/if}
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
    <p class="text-slate-400">Qualified design: {view.job?.result?.qualified_case.label}</p>
    <p class="text-slate-400">Force-vector norm gates: 2% refinement, 5% independent agreement, 1e-8 N floor. Componentwise relative accuracy and interpolation are not qualified.</p>
    <p class="break-all text-slate-400">Request SHA256: {view.job?.request_sha256}</p>
    <p class="break-all text-slate-400">Evidence: {view.job?.evidence_directory}</p>
  {/if}
</section>
