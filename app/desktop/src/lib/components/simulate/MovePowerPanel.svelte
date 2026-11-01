<script lang="ts">
  import { onDestroy, untrack } from "svelte";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { PowerRequirementsInput } from "../../powerRequirements";
  import {
    moveTraceCsv, phaseElectricalCsv, forceSweepCsv, powerModelSnapshot,
    powerRequirements, powerRequirementsCsv,
  } from "../../powerRequirements";
  import { MovePowerJob, moveInputKey } from "../../movePowerJob";
  import { buildMoveRequest, defaultMoveForm, designFullTravelMm, moveAnalysisConfig, moveFormFromRequest, moveFormIssues, type MoveFormInput, type MoveDesignDefaults } from "../../moveForm";
  import { summariseMove } from "../../moveSummary";
  import { moveReportHtml, moveReportMarkdown, type MoveReportMeta } from "../../moveReport";
  import { practicalMoveEstimate } from "../../practicalMoveEstimate";
  import { analyzeDrive } from "../../ipc/physics";
  import { saveTextToFile } from "../../files";
  import { formatSi } from "../../format";
  import MovePowerTrace from "./MovePowerTrace.svelte";
  import { version } from "../../../../package.json";

  let { input, config, designName = "Untitled design", onOpenFieldSettings }: {
    input: PowerRequirementsInput;
    config: ConfigStore;
    designName?: string;
    onOpenFieldSettings?: () => void;
  } = $props();

  let revision = $state(0);
  const job = new MovePowerJob(() => { revision += 1; });
  onDestroy(() => job.dispose());

  function designDefaults(): MoveDesignDefaults {
    return {
      fullTravelMm: designFullTravelMm({ desired_travel_mm: config.desired_travel_mm, active_area_length_mm: config.active_area_length_mm }),
      magnetWidthMm: config.magnet_width_mm,
      massG: config.carriage_mass_kg * 1000,
      frictionN: config.friction_n,
      massSource: config.carriage_mass_source,
    };
  }

  let form = $state<MoveFormInput>(untrack(() => config.power_move
    ? moveFormFromRequest(config.power_move, designDefaults())
    : defaultMoveForm(designDefaults())));
  const design = $derived(designDefaults());
  const issues = $derived(moveFormIssues(form, design));
  let preparing = $state(false);
  let preparingLabel = $state("");
  let attempt = 0;
  let error = $state("");
  let fallbackNote = $state("");
  let saving = $state(false);
  let message = $state("");
  let saveFailure = $state("");
  let exportOpen = $state(false);

  const hasStack = $derived(!!input.config.backplane && (input.config.backplane.layers.length > 0 || input.config.backplane.housing != null));
  let excludeStack = $state(untrack(() => !!input.config.backplane && (input.config.backplane.layers.length > 0 || input.config.backplane.housing != null)));

  const status = $derived.by(() => { revision; return job.status; });
  const jobError = $derived.by(() => { revision; return job.error; });
  const result = $derived.by(() => { revision; return job.result; });
  const pending = $derived(status === "pending" || preparing);

  const analysisConfig = $derived(moveAnalysisConfig(input.config, excludeStack));
  const displayName = $derived((designName || "Untitled design").replace(/\.(pmmotor|pmsensor)$/i, ""));
  const matched = $derived.by(() => {
    const r = input.native ? result : null;
    if (!r || !config.power_move) return null;
    const expected = moveInputKey({
      topology: input.topology, config: analysisConfig, drive: input.driveSettings,
      cad_geometry: input.cadGeometry, move_request: config.power_move,
    });
    return moveInputKey(r.inputs) === expected ? r : null;
  });
  const exclusions = $derived.by(() => matched && matched.inputs.config.backplane == null && input.config.backplane != null
    ? ["Backplane and housing are left out of this calculation. They stay in the saved design and receive no power result."]
    : []);
  const summary = $derived(matched ? summariseMove(matched, { exclusions }) : null);
  const reportInput = $derived.by((): PowerRequirementsInput | null => matched ? {
    ...input, config: matched.inputs.config, drive: matched.result.drive,
    sweep: exclusions.length ? null : input.sweep,
    moveRequest: matched.inputs.move_request, moveResult: matched,
  } : null);
  const canCalculate = $derived(input.native && input.topology === "linear" && issues.length === 0 && (!hasStack || excludeStack) && !pending);
  const savedCustomLoss = $derived(!!config.power_move?.loss_model && config.power_move.loss_model.basis !== "engineering_estimate");

  // Editing the visible move invalidates a previous result and its exports.
  let editFingerprint = untrack(() => JSON.stringify($state.snapshot(form)));
  let savedFingerprint = untrack(() => JSON.stringify(config.power_move ?? null));
  $effect(() => {
    const fingerprint = JSON.stringify($state.snapshot(form));
    if (fingerprint === editFingerprint) return;
    editFingerprint = fingerprint;
    job.setInputs(null);
    error = "";
    fallbackNote = "";
    message = "";
  });
  $effect(() => {
    const fingerprint = JSON.stringify(config.power_move ?? null);
    if (fingerprint === savedFingerprint) return;
    savedFingerprint = fingerprint;
    form = config.power_move ? moveFormFromRequest(config.power_move, designDefaults()) : defaultMoveForm(designDefaults());
    editFingerprint = JSON.stringify($state.snapshot(form));
    job.setInputs(null);
    message = "";
  });

  function fullTravel(): void {
    form.fromMm = 0;
    form.toMm = Number(design.fullTravelMm.toFixed(6));
  }

  async function calculate(): Promise<void> {
    if (!canCalculate) return;
    error = "";
    fallbackNote = "";
    message = "";
    const generation = ++attempt;
    preparing = true;
    preparingLabel = "Reading the active winding";
    try {
      const request = buildMoveRequest(form, { design });
      const cfg = analysisConfig;
      const kf = input.sweep && input.sweep.current_a > 0 ? Math.abs(input.sweep.mean_thrust_n) / input.sweep.current_a : null;
      const analysis = await analyzeDrive(cfg, input.driveSettings, kf, input.cadGeometry);
      if (generation !== attempt) return;
      preparingLabel = "Building the move estimate";
      try {
        request.loss_model = practicalMoveEstimate(cfg, input.driveSettings, analysis);
      } catch (estimateError) {
        // Keep the usable motor and FET-conduction result, but never present
        // it as a complete total.
        request.loss_model = null;
        fallbackNote = estimateError instanceof Error ? estimateError.message : String(estimateError);
      }
      config.power_move = request;
      savedFingerprint = JSON.stringify(config.power_move);
      const inputs = {
        topology: input.topology, config: cfg, drive: $state.snapshot(input.driveSettings),
        cad_geometry: input.cadGeometry, move_request: request,
      };
      job.setInputs(inputs);
      if (generation !== attempt) return;
      await job.run();
    } catch (e) {
      if (generation === attempt) error = e instanceof Error ? e.message : String(e);
    } finally {
      if (generation === attempt) {
        preparing = false;
        preparingLabel = "";
      }
    }
  }

  /** Cancels the winding preparation as well as a running move calculation. */
  function cancelCalculation(): void {
    attempt += 1;
    preparing = false;
    preparingLabel = "";
    job.cancel();
  }

  function reportMeta(r: NonNullable<typeof matched>): MoveReportMeta {
    const c = r.inputs.config, s = r.inputs.drive;
    return {
      designName: c.name?.trim() || displayName,
      geometrySource: r.inputs.cad_geometry
        ? `Imported copper from ${r.inputs.cad_geometry.source_file_name}`
        : `Generated ${c.routing_pattern} routing, ${c.num_layers} copper layers`,
      appVersion: version,
      inputSha256: r.input_sha256,
      driverName: s.driver.name,
      supplyVoltageV: c.supply_voltage_v,
      pwmHz: s.pwm_hz,
      windingTempC: s.winding_temp_c,
      modelVersion: r.result.demand.model_version,
      generatedAt: new Date().toISOString(),
      request: r.inputs.move_request,
    };
  }

  function slug(): string {
    const name = matched?.inputs.config.name?.trim() || displayName;
    return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "design";
  }

  async function save(kind: "html" | "md" | "trace" | "electrical" | "force" | "model" | "requirements"): Promise<void> {
    const r = matched, ri = reportInput, s = summary;
    if (!r || !ri || !s || saving) return;
    const content = kind === "html" ? moveReportHtml(s, reportMeta(r))
      : kind === "md" ? moveReportMarkdown(s, reportMeta(r))
      : kind === "trace" ? moveTraceCsv(ri)
      : kind === "electrical" ? phaseElectricalCsv(r.result.drive)
      : kind === "force" ? (input.sweep ? forceSweepCsv(input.sweep) : null)
      : kind === "model" ? powerModelSnapshot(ri)
      : powerRequirementsCsv(powerRequirements(ri));
    if (content === null) return;
    const extension = kind === "html" ? "html" : kind === "md" ? "md" : kind === "model" ? "json" : "csv";
    const filename = kind === "html" || kind === "md"
      ? `${slug()}-move-report.${extension}`
      : `${slug()}-move-${kind}.${extension}`;
    saving = true;
    saveFailure = "";
    message = "";
    try {
      const path = await saveTextToFile(content, filename, [extension]);
      if (path) message = `Saved ${path}`;
    } catch (e) {
      saveFailure = `Could not save: ${e instanceof Error ? e.message : String(e)}`;
    } finally {
      saving = false;
    }
  }

  const statusTone: Record<string, string> = {
    pass: "text-emerald-300", warn: "text-amber-300", fail: "text-rose-300", unknown: "text-slate-400",
  };
  const statusText: Record<string, string> = { pass: "Pass", warn: "Marginal", fail: "Fail", unknown: "Not evaluated" };
</script>

<section class="min-w-0 space-y-4" aria-label="Move and power">
  <header class="space-y-1">
    <h2 class="text-base font-semibold text-slate-100">Move &amp; power</h2>
    <p class="max-w-3xl text-xs leading-relaxed text-slate-400">
      Enter the fader move and calculate its power from the active copper. The motion is smooth, with zero speed at both ends. Nothing is stored until you calculate.
    </p>
  </header>

  {#if !input.native}
    <p class="rounded border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200" role="status">Demo mode. Move power needs the desktop app and the active design; browser results are not available.</p>
  {/if}
  {#if input.topology !== "linear"}
    <p class="rounded border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200" role="status">Move power supports one linear track. Rotary motion is not supported.</p>
  {/if}

  <div class="space-y-3 rounded border border-slate-700 bg-slate-800/40 p-3">
    <div class="flex flex-wrap items-end gap-2">
      <label class="flex flex-col gap-1 text-xs text-slate-400">From
        <span class="flex items-baseline gap-1">
          <input type="number" min="0" step="0.1" aria-label="Move start in millimetres" bind:value={form.fromMm}
            class="w-24 rounded border border-slate-600 bg-slate-900 px-2 py-1.5 font-mono text-sm text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400" />
          <span class="text-slate-500">mm</span>
        </span>
      </label>
      <label class="flex flex-col gap-1 text-xs text-slate-400">To
        <span class="flex items-baseline gap-1">
          <input type="number" min="0" step="0.1" aria-label="Move end in millimetres" bind:value={form.toMm}
            class="w-24 rounded border border-slate-600 bg-slate-900 px-2 py-1.5 font-mono text-sm text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400" />
          <span class="text-slate-500">mm</span>
        </span>
      </label>
      <label class="flex flex-col gap-1 text-xs text-slate-400">Travel time
        <span class="flex items-baseline gap-1">
          <input type="number" min="0.001" step="0.01" aria-label="Move duration in seconds" bind:value={form.durationS}
            class="w-24 rounded border border-slate-600 bg-slate-900 px-2 py-1.5 font-mono text-sm text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400" />
          <span class="text-slate-500">s</span>
        </span>
      </label>
      <button type="button" onclick={fullTravel} class="rounded border border-slate-600 px-2.5 py-1.5 text-xs text-slate-200 hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Full travel</button>
      <div class="ml-auto flex items-center gap-2">
        <button type="button" disabled={!canCalculate} onclick={calculate}
          class="rounded border border-emerald-500 bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">
          {pending ? (preparingLabel || "Calculating…") : "Calculate power"}
        </button>
        {#if pending}<button type="button" onclick={cancelCalculation} class="rounded border border-slate-600 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Cancel</button>{/if}
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-300">
      {#if form.loadMode === "design"}
        <span>{design.massG.toFixed(2)} g {config.carriage_mass_source === "assembly" ? "full moving assembly" : "magnets only"} · {design.frictionN.toFixed(3)} N sliding friction</span>
        <button type="button" onclick={() => { form.massG = design.massG; form.frictionN = design.frictionN; form.loadMode = "custom"; }} class="text-sky-300 underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Edit load</button>
      {:else}
        <label class="flex items-center gap-1">Mass
          <input type="number" min="0.001" step="0.1" aria-label="Move moving mass in grams" bind:value={form.massG}
            class="w-20 rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400" /> g
        </label>
        <label class="flex items-center gap-1">Friction
          <input type="number" min="0" step="0.005" aria-label="Move friction in newtons" bind:value={form.frictionN}
            class="w-20 rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400" /> N
        </label>
        <button type="button" onclick={() => { form.loadMode = "design"; form.massG = design.massG; form.frictionN = design.frictionN; }} class="text-sky-300 underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Use design load</button>
      {/if}
      <span class="text-slate-500">·</span>
      <span>{formatSi(input.config.supply_voltage_v, "V")} · {input.driveSettings.driver.name} · {formatSi(input.driveSettings.pwm_hz, "Hz")} PWM</span>
    </div>

    {#if hasStack}
      <div class="rounded border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs text-amber-100">
        <p>This design has a backplane or housing. The move model cannot include their dynamic losses.</p>
        <label class="mt-1.5 flex items-start gap-2">
          <input type="checkbox" bind:checked={excludeStack} class="mt-0.5 accent-amber-400" />
          <span>Calculate this move without them. The saved design is not changed and the report records the exclusion.</span>
        </label>
        {#if !excludeStack}<p class="mt-1">Unchecked: calculate is unavailable because results would leave out material effects.</p>{/if}
      </div>
    {/if}

    {#if issues.length}
      <ul class="space-y-0.5 text-xs text-amber-300" aria-live="polite">
        {#each issues as issue (issue)}<li>{issue}</li>{/each}
      </ul>
    {/if}
    {#if error}<p class="text-xs text-rose-300" role="alert">{error}</p>{/if}
    {#if jobError}<p class="text-xs text-rose-300" role="alert">{jobError}</p>{/if}
    {#if fallbackNote}<p class="text-xs text-amber-300">Complete loss estimate unavailable. {fallbackNote} Showing motor and FET conduction only.</p>{/if}

    <details class="text-xs text-slate-400">
      <summary class="cursor-pointer text-slate-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Advanced move settings</summary>
      <div class="mt-2 grid gap-2 sm:grid-cols-2">
        <label class="flex items-center justify-between gap-2">Start speed
          <span><input type="number" step="0.01" aria-label="Start speed in metres per second" bind:value={form.advanced.initialVelocityMPerS} class="w-20 rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-slate-100" /> m/s</span>
        </label>
        <label class="flex items-center justify-between gap-2">End speed
          <span><input type="number" step="0.01" aria-label="End speed in metres per second" bind:value={form.advanced.finalVelocityMPerS} class="w-20 rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-slate-100" /> m/s</span>
        </label>
        <label class="flex items-center justify-between gap-2">Damping
          <span><input type="number" step="0.01" min="0" aria-label="Viscous damping" bind:value={form.advanced.dampingNsPerM} class="w-20 rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-slate-100" /> N·s/m</span>
        </label>
        <label class="flex items-center justify-between gap-2">Added load
          <span><input type="number" step="0.01" aria-label="Signed external load" bind:value={form.advanced.externalLoadN} class="w-20 rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-slate-100" /> N</span>
        </label>
        <label class="flex items-center justify-between gap-2">Electrical reference
          <span><input type="number" step="0.0001" aria-label="Controller electrical reference in radians" bind:value={form.advanced.electricalAngleRad} class="w-24 rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-slate-100" /> rad</span>
        </label>
        <label class="flex items-center justify-between gap-2">Force-map positions
          <input type="number" step="1" min="2" max="513" aria-label="Force-map positions" bind:value={form.advanced.forcePositions} class="w-20 rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-slate-100" />
        </label>
        <label class="flex items-center justify-between gap-2">Time step
          <span><input type="number" step="0.00001" min="0.00001" aria-label="Time step in seconds" placeholder="auto"
            value={form.advanced.timeStepS ?? ""} oninput={(e) => { const v = e.currentTarget.value; form.advanced.timeStepS = v === "" ? null : Number(v); }}
            class="w-24 rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-slate-100" /> s</span>
        </label>
        <label class="flex items-center gap-2">
          <input type="checkbox" bind:checked={form.advanced.acceptsRegeneration} class="accent-emerald-400" />
          Supply can absorb returned energy
        </label>
      </div>
      <p class="mt-2 text-slate-500">Positions are measured from the start of travel. The electrical reference belongs to the controller, not the design; change it only if you know the winding polarity.</p>
      {#if savedCustomLoss}
        <p class="mt-2 text-amber-300">This saved move has its own loss declaration. Calculate replaces it with the current engineering estimate. Export data first if you need the old declaration.</p>
      {/if}
      {#if onOpenFieldSettings}<button type="button" onclick={onOpenFieldSettings} class="mt-2 text-sky-300 underline-offset-2 hover:underline">Field and loss settings</button>{/if}
    </details>
  </div>

  {#if summary && matched}
    <section class="space-y-3" aria-label="Move power results">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h3 class="text-sm font-semibold text-slate-100">Power for this move</h3>
        <span class="rounded border px-2 py-0.5 text-[11px] font-semibold {summary.scope === 'Engineering estimate' ? 'border-sky-500/50 bg-sky-500/10 text-sky-200' : 'border-amber-500/50 bg-amber-500/10 text-amber-200'}">{summary.scope}</span>
      </div>
      <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {#each [["Peak supply draw", summary.headline.peakPower], ["Average during the move", summary.headline.averagePower], ["Energy per move", summary.headline.energy], ["Peak supply current", summary.headline.peakSupplyCurrent]] as [label, value] (label)}
          <div class="rounded border border-slate-700 bg-slate-800/50 px-3 py-2">
            <div class="font-mono text-xl text-slate-100">{value}</div>
            <div class="text-[11px] leading-snug text-slate-400">{label}</div>
          </div>
        {/each}
      </div>
      <p class="text-xs leading-relaxed text-slate-400">{summary.scopeText}</p>
      <div class="grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div class="rounded border border-slate-700 bg-slate-900/40 p-2">
          <h4 class="px-1 pb-1 text-xs text-slate-400">Power over time</h4>
          <MovePowerTrace samples={matched.result.demand.samples} supply={!!matched.result.demand.source} />
        </div>
        <dl class="grid grid-cols-2 content-start gap-x-3 gap-y-1.5 text-xs">
          <dt class="text-slate-400">Distance</dt><dd class="text-right font-mono text-slate-200">{summary.motion.distance}</dd>
          <dt class="text-slate-400">Duration</dt><dd class="text-right font-mono text-slate-200">{summary.motion.duration}</dd>
          <dt class="text-slate-400">Peak speed</dt><dd class="text-right font-mono text-slate-200">{summary.motion.peakSpeed}</dd>
          <dt class="text-slate-400">Peak acceleration</dt><dd class="text-right font-mono text-slate-200">{summary.motion.peakAcceleration}</dd>
          <dt class="text-slate-400">Peak motor force</dt><dd class="text-right font-mono text-slate-200">{summary.motion.peakForce}</dd>
          <dt class="text-slate-400">Phase peak</dt><dd class="text-right font-mono text-slate-200">{summary.electrical.phasePeak}</dd>
          {#if summary.electrical.phasePeakIncludingRipple}
            <dt class="text-slate-400">Phase peak with ripple</dt><dd class="text-right font-mono text-slate-200">{summary.electrical.phasePeakIncludingRipple}</dd>
          {/if}
        </dl>
      </div>

      <div class="space-y-1.5">
        {#each summary.checks as check (check.label)}
          <div class="flex items-start gap-2 text-xs">
            <span class="mt-0.5 w-16 shrink-0 font-semibold {statusTone[check.status]}">{statusText[check.status]}</span>
            <div class="min-w-0">
              <span class="text-slate-200">{check.label}:</span> <span class="font-mono text-slate-300">{check.reading}</span>
              {#if check.status !== "pass"}<p class="mt-0.5 leading-snug text-slate-400">{check.detail}</p>{/if}
            </div>
          </div>
        {/each}
      </div>

      {#if summary.exclusions.length || summary.omissions.length}
        <details class="rounded border border-amber-500/30 bg-amber-500/5 p-2.5 text-xs">
          <summary class="cursor-pointer text-amber-200">What this estimate leaves out ({summary.exclusions.length + summary.omissions.length})</summary>
          <ul class="mt-1.5 space-y-1 text-amber-100/80">
            {#each summary.exclusions as item (item)}<li>{item}</li>{/each}
            {#each summary.omissions as item (item)}<li>{item}</li>{/each}
          </ul>
        </details>
      {/if}

      <div class="flex flex-wrap items-center gap-2">
        <button type="button" disabled={saving} onclick={() => save("html")}
          class="rounded border border-emerald-500 bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Save report</button>
        <button type="button" aria-expanded={exportOpen} onclick={() => (exportOpen = !exportOpen)}
          class="rounded border border-slate-600 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Export data</button>
        {#if summary.hasCompleteModel === false}<span class="text-xs text-amber-300">Partial estimate: totals omit unknown losses.</span>{/if}
      </div>
      {#if exportOpen}
        <div class="flex flex-wrap gap-2 rounded border border-slate-700 bg-slate-800/40 p-2">
          {#each [
            ["md", "Report (Markdown)"], ["trace", "Move time series CSV"], ["electrical", "Winding electrical CSV"],
            ["force", "Force sweep CSV"], ["model", "Reproducibility JSON"], ["requirements", "Requirements CSV"],
          ] as const as [kind, label] (kind)}
            <button type="button" disabled={saving} onclick={() => save(kind)} class="rounded border border-slate-600 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-700 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">{label}</button>
          {/each}
        </div>
      {/if}
      {#if message}<p class="break-all text-xs text-emerald-300" role="status">{message}</p>{/if}
      {#if saveFailure}<p class="text-xs text-rose-300" role="alert">{saveFailure}</p>{/if}
    </section>
  {:else if pending}
    <p class="text-xs text-slate-400" role="status">Calculating from the active copper. Cancellation takes effect at the next solver checkpoint.</p>
  {:else if status === "cancelled"}
    <p class="text-xs text-slate-400">Calculation cancelled. Define or adjust the move to calculate again.</p>
  {:else}
    <p class="text-xs leading-relaxed text-slate-500">Choose Calculate to estimate peak and average power, energy and the supply current for this move. The design's own mass and friction are used unless you edit the load.</p>
  {/if}
</section>
