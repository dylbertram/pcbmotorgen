<script lang="ts">
  import type { PowerRequirementsInput } from "../../powerRequirements";
  import { powerRequirements, powerReportMarkdown, powerRequirementsCsv, forceSweepCsv, phaseElectricalCsv, powerModelSnapshot, currentMoveResult, moveTraceCsv } from "../../powerRequirements";
  import { saveTextToFile } from "../../files";
  import { onDestroy, untrack } from "svelte";
  import type { ConfigStore } from "../../stores/config.svelte";
  import { MovePowerJob } from "../../movePowerJob";
  import { emptyMoveTemplate, parseMoveRequest } from "../../movePowerInputs";

  let { input, config }: { input: PowerRequirementsInput; config: ConfigStore } = $props();
  let revision = $state(0);
  const job = new MovePowerJob(() => { revision += 1; });
  onDestroy(() => job.dispose());
  let applied = $derived(config.power_move ? JSON.stringify(config.power_move, null, 2) : emptyMoveTemplate());
  let draft = $derived(applied);
  let editing = $derived(draft !== applied);
  let moveError = $state("");
  const moveStatus = $derived.by(() => { revision; return job.status; });
  const jobError = $derived.by(() => { revision; return job.error; });
  const result = $derived.by(() => { revision; return job.result; });
  const activeInputs = $derived(input.native && !editing && config.power_move ? {
    topology: input.topology, config: input.config, drive: input.driveSettings,
    cad_geometry: input.cadGeometry, move_request: config.power_move,
  } : null);
  let reportInput = $derived({ ...input, moveRequest: editing ? null : config.power_move, moveResult: result });
  let matchedMove = $derived(currentMoveResult(reportInput));
  let sections = $derived(powerRequirements(reportInput));
  $effect(() => {
    const snapshot = activeInputs ? JSON.parse(JSON.stringify(activeInputs)) : null;
    untrack(() => job.setInputs(snapshot));
  });
  function applyMove(): void {
    job.setInputs(null);
    moveError = "";
    try { config.power_move = parseMoveRequest(draft); draft = JSON.stringify(config.power_move, null, 2); }
    catch (error) { moveError = error instanceof Error ? error.message : String(error); }
  }
  let saving = $state(false);
  let message = $state("");
  let failure = $state("");
  let exports = $derived([
    { kind: "report", label: "Download report", available: true },
    { kind: "summary", label: "Requirements CSV", available: true },
    { kind: "model", label: "Model snapshot JSON", available: true },
    { kind: "force", label: "Force sweep CSV", available: input.native && !!input.sweep },
    { kind: "electrical", label: "Phase electrical CSV", available: input.native && !!input.drive },
    { kind: "trace", label: "Move time-series CSV", available: !!matchedMove },
  ] as const);

  async function download(kind: "report" | "summary" | "model" | "force" | "electrical" | "trace"): Promise<void> {
    if (saving) return;
    const freshInput = { ...input, moveRequest: editing ? null : config.power_move, moveResult: job.result };
    const freshSections = powerRequirements(freshInput);
    const content = kind === "report" ? powerReportMarkdown(freshSections)
      : kind === "summary" ? powerRequirementsCsv(freshSections)
      : kind === "model" ? powerModelSnapshot(freshInput)
      : kind === "trace" ? moveTraceCsv(freshInput)
      : kind === "force" && input.native && input.sweep ? forceSweepCsv(input.sweep)
      : kind === "electrical" && input.native && input.drive ? phaseElectricalCsv(input.drive) : null;
    if (content === null) return;
    const extension = kind === "report" ? "md" : kind === "model" ? "json" : "csv";
    const filename = `power-requirements-${kind}.${extension}`;
    saving = true;
    message = "";
    failure = "";
    try {
      if (input.native) {
        const path = await saveTextToFile(content, filename, [extension]);
        if (path) message = `Saved ${path}`;
      } else {
        const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename;
        anchor.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        message = `Downloaded ${filename}`;
      }
    } catch (error) {
      failure = `Could not save export: ${error instanceof Error ? error.message : String(error)}`;
    } finally {
      saving = false;
    }
  }
</script>

<section class="min-w-0 space-y-4" aria-label="Power requirements">
  <header class="space-y-2">
    <h2 class="text-base font-semibold text-slate-100">Power requirements</h2>
    <p class="max-w-3xl text-xs leading-relaxed text-slate-400">
      Inputs and results for one linear drive. Define an explicit move for native time-domain demand.
      Static copper loss alone is not maximum input power. Modeled scenario peaks are not guaranteed maxima.
    </p>
    {#if !input.native}
      <p class="rounded border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200" role="status">Demo mode. Browser mock results are excluded from this report. Run the desktop app for native simulation results.</p>
    {/if}
  </header>
  <details class="rounded border border-slate-700 bg-slate-800/40 p-3">
    <summary class="cursor-pointer text-sm text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400">Move definition and calculation</summary>
    <div class="mt-3 space-y-3 text-xs text-slate-400">
      <p>Specify the move in SI units using the JSON editor. Replace every required null, state the mass breakdown and choose the source's return capability. Existing designs have no inferred move. Applying this definition adds it to the saved design.</p>
      <p>Positions are absolute first-magnet-center coordinates in metres. The profile is imposed quintic motion with zero endpoint acceleration. Control explicitly uses balanced-star sinusoidal currents, independent of the static preview. The source is directly at a constant-voltage DC link. Keep additional_driver_loss_w null when switching, dead-time and control losses are unknown. Zero declares an idealized scenario, not hardware total power.</p>
      <label class="block space-y-1"><span>Move model JSON</span>
        <textarea aria-label="Move model JSON" rows="14" spellcheck="false" bind:value={draft} oninput={() => { job.setInputs(null); moveError = ""; }} class="w-full rounded border border-slate-600 bg-slate-900 p-2 font-mono text-xs text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400"></textarea>
      </label>
      <div class="flex flex-wrap gap-2">
        <button type="button" onclick={applyMove} class="rounded border border-slate-600 px-3 py-1.5 text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400">Apply move definition</button>
        <button type="button" disabled={!input.native || input.topology !== "linear" || editing || !config.power_move || moveStatus === "pending"} onclick={() => { job.setInputs(activeInputs); void job.run(); }} class="rounded border border-sky-500/60 px-3 py-1.5 text-sky-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400 disabled:opacity-40">Calculate move power</button>
        <button type="button" disabled={moveStatus !== "pending"} onclick={() => job.cancel()} class="rounded border border-slate-600 px-3 py-1.5 text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400 disabled:opacity-40">Cancel calculation</button>
        <button type="button" onclick={() => { job.setInputs(null); config.power_move = null; draft = emptyMoveTemplate(); moveError = ""; }} class="rounded border border-slate-600 px-3 py-1.5 text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400">Clear move definition</button>
      </div>
      {#if editing}<p>Unapplied move draft. Previous move results and exports are unavailable.</p>{/if}
      {#if input.topology !== "linear"}<p>Move power supports one linear track. Rotary motion is not supported.</p>{/if}
      {#if moveStatus === "pending"}<p role="status">Calculating from the active copper and move inputs. Cancellation takes effect at the next solver checkpoint.</p>{/if}
      {#if moveStatus === "cancelled"}<p>Calculation cancelled. No retained move results are available.</p>{/if}
      {#if moveError || jobError}<p role="alert" class="text-rose-300">{moveError || jobError}</p>{/if}
      {#if matchedMove && !matchedMove.result.demand.feasible}<p role="alert" class="text-amber-200">Requested motion is not achieved. {matchedMove.result.demand.limiting_factors.join(". ")} The trace contains required commands, not achieved motion.</p>{/if}
    </div>
  </details>
  <div class="flex flex-wrap gap-2" aria-label="Power requirements exports">
    {#each exports as item (item.kind)}
      <button type="button" disabled={saving || !item.available} onclick={() => download(item.kind)} class="rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-40">{item.label}</button>
    {/each}
  </div>
  {#if message}<p role="status" class="break-all text-xs text-emerald-300">{message}</p>{/if}
  {#if failure}<p role="alert" class="text-xs text-rose-300">{failure}</p>{/if}
  <p class="text-xs text-slate-400">Unknown means unavailable, not zero. Configured values are inputs, not measurements. Force CSV contains force versus position; electrical CSV contains winding resistance and inductance. Move time-series CSV is available only for a current native result and labels infeasible requests explicitly.</p>
  {#each sections as section (section.title)}
    <section class="overflow-hidden rounded-lg border border-slate-700 bg-slate-800/40" aria-label={section.title}>
      <h3 class="border-b border-slate-700 px-4 py-3 text-sm font-semibold text-slate-200">{section.title}</h3>
      <dl class="divide-y divide-slate-700/60">
        {#each section.rows as row (row.label)}
          <div class="grid gap-1 px-4 py-3 text-xs sm:grid-cols-[minmax(10rem,1fr)_minmax(0,2fr)] sm:gap-4">
            <dt class="text-slate-400">{row.label}</dt>
            <dd class="min-w-0 space-y-1">
              <div class="flex flex-wrap items-baseline gap-2"><span class={["break-words font-medium text-slate-100", { unknown: row.source === "Unknown" }]}>{row.value}</span>{#if row.source !== "Unknown"}<span class="text-slate-500">{row.source}</span>{/if}</div>
              <p class="break-words leading-relaxed text-slate-400">{row.detail}</p>
            </dd>
          </div>
        {/each}
      </dl>
    </section>
  {/each}
</section>

<style>
  .unknown { color: #fcd34d; }
</style>
