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
    { key: "min_trace_mm", id: "motor-trace-width", label: "Minimum trace width (mm)", min: 0.01 },
    { key: "min_space_mm", id: "motor-trace-gap", label: "Minimum trace gap (mm)", min: 0.01 },
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
    <h4 class="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-300">
      Traces &amp; Board
    </h4>

    <div class="grid gap-x-3 gap-y-2.5 sm:grid-cols-2">
      {#each sizingFields as field (field.key)}
        <label class="min-w-0">
          <span class="flex items-center justify-between gap-2">
            <span class="min-w-0 text-xs text-slate-300">
              {field.label}
            </span>
            <NumberField
              id={field.id}
              value={field.key === "min_trace_mm" ? traceWidthMm ?? config.min_trace_mm : config[field.key]}
              min={field.min}
              step={0.01}
              ariaLabel={field.label}
              class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
              onCommit={(value) => {
                if (field.key === "min_trace_mm" && onTraceWidthChange) onTraceWidthChange(value);
                else config[field.key] = value;
              }}
            />
          </span>
        </label>
      {/each}
    </div>
    <p class="mt-2 text-[11px] text-slate-500">
      Trace width sizes the copper around each centerline. Gap is the minimum manufacturing clearance. Via dimensions apply to generated and imported paths.
    </p>
    <ViaSizingGuide holeMm={config.min_via_drill_mm} ringMm={config.min_via_annular_ring_mm}>
      {#each viaFields as field (field.key)}
        <label class="min-w-0 flex items-center justify-between gap-2">
          <span class="min-w-0 text-xs text-slate-300">
            {field.label}
            {#if field.key === "min_via_drill_mm"}
              <HelpTag label="About via hole size" tip="The diameter of the drilled hole, excluding the surrounding copper ring. This is not the outer via diameter." />
            {:else}
              <HelpTag label="About annular ring width" tip="Copper width on one side of the hole. A 0.075 mm ring adds 0.15 mm to the via diameter, because it surrounds both sides." />
            {/if}
          </span>
          <NumberField id={field.id} value={config[field.key]} min={field.min} step={0.01}
            ariaLabel={field.label} class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
            onCommit={(value) => config[field.key] = value} />
        </label>
      {/each}
    </ViaSizingGuide>
  </div>
</div>
