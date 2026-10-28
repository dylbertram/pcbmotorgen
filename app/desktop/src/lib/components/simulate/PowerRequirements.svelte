<script lang="ts">
  import type { PowerRequirementsInput } from "../../powerRequirements";
  import { powerRequirements, powerReportMarkdown, powerRequirementsCsv, forceSweepCsv, phaseElectricalCsv, powerModelSnapshot } from "../../powerRequirements";
  import { saveTextToFile } from "../../files";

  let { input }: { input: PowerRequirementsInput } = $props();
  let sections = $derived(powerRequirements(input));
  let saving = $state(false);
  let message = $state("");
  let failure = $state("");
  let exports = $derived([
    { kind: "report", label: "Download report", available: true },
    { kind: "summary", label: "Requirements CSV", available: true },
    { kind: "model", label: "Model snapshot JSON", available: true },
    { kind: "force", label: "Force sweep CSV", available: input.native && !!input.sweep },
    { kind: "electrical", label: "Phase electrical CSV", available: input.native && !!input.drive },
  ] as const);

  async function download(kind: "report" | "summary" | "model" | "force" | "electrical"): Promise<void> {
    if (saving) return;
    const content = kind === "report" ? powerReportMarkdown(sections)
      : kind === "summary" ? powerRequirementsCsv(sections)
      : kind === "model" ? powerModelSnapshot(input)
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
      Inputs and results for one linear drive. The current model provides static force and electrical checks,
      not a time-domain move or supply-current calculation. Copper loss alone is not maximum input power.
    </p>
    {#if !input.native}
      <p class="rounded border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200" role="status">Demo mode. Browser mock results are excluded from this report. Run the desktop app for native simulation results.</p>
    {/if}
  </header>
  <div class="flex flex-wrap gap-2" aria-label="Power requirements exports">
    {#each exports as item (item.kind)}
      <button type="button" disabled={saving || !item.available} onclick={() => download(item.kind)} class="rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-40">{item.label}</button>
    {/each}
  </div>
  {#if message}<p role="status" class="break-all text-xs text-emerald-300">{message}</p>{/if}
  {#if failure}<p role="alert" class="text-xs text-rose-300">{failure}</p>{/if}
  <p class="text-xs text-slate-400">Unknown means unavailable, not zero. Configured values are inputs, not measurements. Force CSV contains force versus position; electrical CSV contains winding resistance and inductance. Neither is a time series.</p>
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
