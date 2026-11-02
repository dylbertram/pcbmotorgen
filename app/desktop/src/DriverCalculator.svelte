<script lang="ts">
  import { onMount } from "svelte";
  import { calculateDriver, emptyDriverInput, type DriverCalculatorInput, type DriverCalculatorSnapshot } from "./lib/driver/driverCalculator";
  import { calculatorSeed, listenDriverImport, requestDriverImport } from "./lib/driver/driverCalculatorWindow";
  import DriverSelector from "./lib/components/simulate/DriverSelector.svelte";
  import { ConfigStore } from "./lib/stores/config.svelte";
  import { errorMessage } from "./lib/utils/errorMessage";
  const config = new ConfigStore();
  let input = $state<DriverCalculatorInput>(emptyDriverInput());
  let source = $state<DriverCalculatorSnapshot | null>(null);
  let error = $state<string | null>(null);
  let importing = $state(false);
  let ready = $state(false);
  let activeRequest: string | null = null;
  let timeout: ReturnType<typeof setTimeout> | undefined;
  const calculatorInput = $derived({ ...input, driver: config.drive.driver });
  const result = $derived(calculateDriver(calculatorInput));
  const edited = $derived(source !== null && JSON.stringify(calculatorInput) !== JSON.stringify(source.input));
  const fields = [
    { key: "resistanceOhm", label: "Hot phase resistance", unit: "Ω", scale: 1 },
    { key: "inductanceH", label: "Synchronous winding inductance", unit: "µH", scale: 1e6 },
    { key: "seriesInductanceH", label: "External series inductance per phase", unit: "µH", scale: 1e6 },
    { key: "currentA", label: "Phase-current amplitude", unit: "A", scale: 1 },
    { key: "busV", label: "Bus voltage", unit: "V", scale: 1 },
    { key: "pwmHz", label: "PWM frequency", unit: "kHz", scale: 1e-3 },
    { key: "speedMS", label: "Target speed", unit: "m/s", scale: 1 },
    { key: "headroom", label: "Usable bus share", unit: "%", scale: 100 },
    { key: "rippleFraction", label: "Ripple limit relative to phase current", unit: "%", scale: 100 },
    { key: "forceConstant", label: "Force constant, optional", unit: "N/A", scale: 1 },
    { key: "electricalPeriodM", label: "Electrical period, optional", unit: "mm", scale: 1000 },
    { key: "ampacityA", label: "Trace ampacity, optional", unit: "A", scale: 1 },
  ] as const;
  const format = (value: number | null | undefined, unit: string) => value == null ? "Not evaluated" : `${Number(value.toPrecision(4))} ${unit}`;
  function apply(snapshot: DriverCalculatorSnapshot): void {
    source = structuredClone(snapshot);
    input = structuredClone(snapshot.input);
    config.drive = { ...config.drive, driver: { ...snapshot.input.driver } };
    error = null;
  }
  async function importMotor(): Promise<void> {
    importing = true; error = null;
    const requestId = crypto.randomUUID();
    activeRequest = requestId;
    clearTimeout(timeout);
    timeout = setTimeout(() => { activeRequest = null; importing = false; error = "The motor window did not respond. Existing calculator inputs are unchanged."; }, 8000);
    try { await requestDriverImport(requestId); }
    catch (e) { if (activeRequest !== requestId) return; activeRequest = null; clearTimeout(timeout); importing = false; error = errorMessage(e); }
  }
  onMount(() => {
    document.title = "Driver calculator";
    const unlisten = listenDriverImport(response => {
      if (response.requestId !== activeRequest) return;
      activeRequest = null;
      clearTimeout(timeout); importing = false;
      if (response.snapshot) apply(response.snapshot);
      else error = response.error;
    });
    void calculatorSeed().then(snapshot => { if (snapshot) apply(snapshot); }).catch(e => error = String(e)).finally(() => ready = true);
    return () => { activeRequest = null; clearTimeout(timeout); void unlisten.then(fn => fn()); };
  });
</script>

<!-- The scroll container must be focusable for keyboard scrolling in WebKit. -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<main class="h-dvh overflow-y-auto overscroll-contain bg-slate-900 p-5 text-slate-100 sm:p-8 lg:flex lg:flex-col lg:overflow-hidden" aria-label="Driver calculator" tabindex="0">
  <header class="mb-6 flex shrink-0 flex-wrap items-start justify-between gap-4 border-b border-slate-700 pb-5">
    <div class="max-w-2xl space-y-2">
      <h1 class="text-xl font-semibold">Driver calculator</h1>
      <p class="text-xs leading-relaxed text-slate-400">Compare a driver with a balanced three-phase star winding. These inputs are independent. Editing them does not change a motor file, and motor edits do not update this window.</p>
      <p class="text-xs text-slate-400">{source ? `Snapshot from ${source.source} · ${new Date(source.capturedAt).toLocaleString()}${edited ? ' · edited in calculator' : ''}` : "Enter winding values manually, or import the active motor's current winding analysis."}</p>
    </div>
    <button type="button" disabled={importing || !ready} onclick={() => void importMotor()} class="rounded border border-slate-600 px-3 py-2 text-xs text-sky-300 hover:bg-slate-800 disabled:opacity-40">{importing ? "Importing…" : "Import active motor"}</button>
  </header>
  {#if error}<p role="alert" class="mb-5 rounded border border-rose-500/40 p-3 text-xs text-rose-300">{error}</p>{/if}
  {#if source}{#each source.notes as note (note)}<p class="mb-3 text-xs text-amber-300">{note}</p>{/each}{/if}
  <div class="grid min-w-0 gap-8 lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]">
    <!-- Independently focusable panes support keyboard scrolling in WebKit. -->
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <section aria-label="Calculator input pane" tabindex="0" class="min-w-0 lg:min-h-0 lg:overflow-y-auto lg:overscroll-contain lg:pr-2">
    <fieldset disabled={!ready} aria-label="Calculator inputs" class="min-w-0 space-y-5">
      <DriverSelector {config} />
      <label class="flex items-center justify-between gap-4 text-xs text-slate-300">Winding connection
        <select aria-label="Calculator winding connection" bind:value={input.connection} class="rounded border border-slate-600 bg-slate-800 px-2 py-1.5 text-slate-100"><option value="star">Star / wye</option><option value="delta">Delta, unsupported</option></select>
      </label>
      {#if input.phaseCount !== 3}<p role="alert" class="text-xs text-amber-300">Imported {input.phaseCount} phases. This three-phase calculator cannot evaluate that source.</p>{/if}
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-1">
        {#each fields as field (field.key)}
          <label class="flex flex-col gap-1.5 text-xs text-slate-400">{field.label} ({field.unit})
            <input type="number" aria-label={`${field.label} (${field.unit})`} min="0" step="any" value={input[field.key] === null ? "" : input[field.key]! * field.scale}
              oninput={event => { const v = event.currentTarget.valueAsNumber; input[field.key] = Number.isFinite(v) ? v / field.scale : null; }}
              class="w-full rounded border border-slate-600 bg-slate-800 px-2.5 py-2 font-mono text-slate-100 focus:border-emerald-500 focus:outline-none" />
          </label>
        {/each}
      </div>
    </fieldset>
    </section>
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <section aria-label="Driver suitability checks" tabindex="0" class="min-w-0 space-y-5 lg:min-h-0 lg:overflow-y-auto lg:overscroll-contain lg:pr-2">
      <h2 class="text-base font-semibold">Suitability at this operating point</h2>
      {#if result.errors.length}
        <div role="status" class="space-y-2 rounded border border-amber-500/40 p-4 text-xs text-amber-300">{#each result.errors as message (message)}<p>{message}</p>{/each}</div>
      {:else}
        <dl class="grid grid-cols-2 gap-4 rounded border border-slate-700 bg-slate-800/40 p-4 text-xs">
          <div><dt class="text-slate-400">Effective phase inductance</dt><dd class="mt-1 font-mono text-emerald-300">{format(result.effectiveH! * 1e6, "µH")}</dd></div>
          <div><dt class="text-slate-400">Winding copper loss, before ripple</dt><dd class="mt-1 font-mono text-slate-200">{format(result.copperW, "W")}</dd></div>
          <div><dt class="text-slate-400">Minimum PWM for ripple limit</dt><dd class="mt-1 font-mono text-slate-200">{format(result.minPwmHz! / 1000, "kHz")}</dd></div>
          <div><dt class="text-slate-400">Additional inductance needed per phase</dt><dd class="mt-1 font-mono text-slate-200">{format(result.addedInductanceH! * 1e6, "µH")}</dd></div>
        </dl>
        <div class="overflow-x-auto rounded border border-slate-700">
          <table class="w-full text-left text-xs" aria-label="Driver checks">
            <thead class="bg-slate-800 text-slate-400"><tr><th class="p-3 font-normal">Check</th><th class="p-3 font-normal">Demand</th><th class="p-3 font-normal">Limit</th><th class="p-3 font-normal">Result</th></tr></thead>
            <tbody>{#each result.checks as check (check.label)}<tr class="border-t border-slate-700"><th scope="row" class="p-3 font-normal text-slate-300">{check.label}</th><td class="whitespace-nowrap p-3 font-mono">{format(check.value, check.unit)}</td><td class="whitespace-nowrap p-3 font-mono">{format(check.limit, check.unit)}</td><td class="p-3 {check.status === 'pass' ? 'text-emerald-300' : check.status === 'fail' ? 'text-rose-300' : 'text-slate-400'}">{check.status === "pass" ? "Pass" : check.status === "fail" ? "Fail" : "Not evaluated"}</td></tr>{/each}</tbody>
          </table>
        </div>
      {/if}
      <aside class="space-y-2 border-t border-slate-700 pt-4 text-xs leading-relaxed text-slate-400" aria-label="Calculator model limits">
        <h3 class="font-semibold text-slate-300">Screening model, not hardware qualification</h3>
        <p>Constant hot resistance and synchronous inductance. Balanced sinusoidal phase-current amplitude, with a 50%-duty RL PWM ripple estimate. The RMS check approximates ripple as triangular. Optional force constant and electrical period enable the at-speed voltage check.</p>
        <p>Supply-current demand, regeneration, switching losses, inductor DCR/core losses, frequency-dependent material effects and temperatures are not calculated. Trace ampacity is an entered limit at its original assumptions, not a new thermal solve. Check datasheet limits and verify the design on hardware.</p>
      </aside>
    </section>
  </div>
</main>
