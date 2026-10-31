<script lang="ts">
  import type { ConfigStore } from "../../../stores/config.svelte";
  import NumberField from "../../ui/NumberField.svelte";
  import HelpTag from "../../ui/HelpTag.svelte";
  import Separator from "../../ui/Separator.svelte";
  import ViaSizingGuide from "../ViaSizingGuide.svelte";

  let { config, traceWidthMm, onTraceWidthChange }: {
    config: ConfigStore;
    traceWidthMm?: number;
    onTraceWidthChange?: (width: number) => void;
  } = $props();

  const sizingFields = [
    { key: "trace_width_mm", id: "motor-trace-width", label: "Trace width (mm)", min: 0.01, help: "Copper width used in the board and DXF. Must be at least the minimum trace width." },
    { key: "min_trace_mm", id: "motor-min-trace-width", label: "Minimum trace width (mm)", min: 0.01, help: "Smallest trace your PCB manufacturer can make." },
    { key: "min_space_mm", id: "motor-trace-gap", label: "Minimum trace gap (mm)", min: 0.01, help: "Smallest allowed clearance between copper traces." },
  ] as const;
  const viaFields = [
    { key: "min_via_drill_mm", id: "motor-via-drill", label: "Via hole size (mm)", min: 0.01 },
    { key: "min_via_annular_ring_mm", id: "motor-via-annular-ring", label: "Annular ring width (mm)", min: 0.01 },
  ] as const;
</script>

<!-- Plain sub-block of the combined "Topology & Board" section. No mode
     gating: every field is a normal editable input. -->
<div>
  <Separator class="bg-slate-700/80" />

  <div class="pt-2.5">
    <h4 class="mb-2 text-xs font-medium text-slate-300">
      Traces &amp; board
    </h4>

    <div class="trace-fields grid gap-x-3 gap-y-2.5">
      {#each sizingFields as field (field.key)}
        <label class="min-w-0">
          <span class="flex items-center justify-between gap-2">
            <span class="min-w-0 text-xs text-slate-300">
              {field.label}
              <HelpTag label={`About ${field.label}`} tip={field.help} />
            </span>
            <NumberField
              id={field.id}
              value={field.key === "trace_width_mm" ? traceWidthMm ?? config.trace_width_mm : config[field.key]}
              min={field.min}
              step={0.01}
              ariaLabel={field.label}
              class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
              onCommit={(value) => {
                if (field.key === "trace_width_mm" && onTraceWidthChange) onTraceWidthChange(value);
                else config[field.key] = value;
              }}
            />
          </span>
        </label>
      {/each}
    </div>
    <ViaSizingGuide holeMm={config.min_via_drill_mm} ringMm={config.min_via_annular_ring_mm}>
      {#each viaFields as field (field.key)}
        <label class="min-w-0 flex items-center justify-between gap-2">
          <span class="min-w-0 text-xs text-slate-300">
            {field.label}
            {#if field.key === "min_via_drill_mm"}
              <HelpTag label="About via hole size" tip="Drilled hole diameter, excluding the copper ring." />
            {:else}
              <HelpTag label="About annular ring width" tip="Copper width on one side of the hole. Both sides count toward the outer diameter." equation={String.raw`D_{\mathrm{via}} = D_{\mathrm{hole}} + 2w_{\mathrm{ring}}`} />
            {/if}
          </span>
          <NumberField id={field.id} value={config[field.key]} min={field.min} step={0.01}
            ariaLabel={field.label} class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
            onCommit={(value) => config[field.key] = value} />
        </label>
      {/each}
      <label class="min-w-0 flex items-center justify-between gap-2">
        <span class="min-w-0 text-xs text-slate-300">
          Via plating (µm)
          <HelpTag label="About via plating" tip="Barrel plating thickness. 25 µm is the IPC class 2 minimum average." />
        </span>
        <NumberField value={Math.round(config.drive.via_plating_m * 1e6)} min={5} max={100} step={5}
          ariaLabel="Via plating thickness (µm)" class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
          onCommit={(value) => config.drive = { ...config.drive, via_plating_m: value * 1e-6 }} />
      </label>
    </ViaSizingGuide>
  </div>
</div>

<style>
  @container (min-width: 560px) {
    .trace-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
</style>
