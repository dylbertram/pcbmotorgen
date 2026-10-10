<script lang="ts">
  import type { ConfigStore } from "../../../stores/config.svelte";
  import NumberField from "../../ui/NumberField.svelte";
  import HelpTag from "../../ui/HelpTag.svelte";
  import Separator from "../../ui/Separator.svelte";

  let { config }: { config: ConfigStore } = $props();

  const sizingFields = [
    { key: "min_trace_mm", id: "motor-trace-width", label: "Minimum trace width (mm)", min: 0.01 },
    { key: "min_space_mm", id: "motor-trace-gap", label: "Minimum trace gap (mm)", min: 0.01 },
    { key: "min_via_drill_mm", id: "motor-via-drill", label: "Via drill (mm)", min: 0.01 },
    { key: "min_via_annular_ring_mm", id: "motor-via-annular-ring", label: "Via annular ring (mm)", min: 0.01 },
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
            <span class="min-w-0 truncate text-xs text-slate-300">{field.label}</span>
            <NumberField
              id={field.id}
              value={config[field.key]}
              min={field.min}
              step={0.01}
              ariaLabel={field.label}
              class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
              onCommit={(value) => (config[field.key] = value)}
            />
          </span>
        </label>
      {/each}
      <label class="min-w-0">
        <span class="flex items-center justify-between gap-2">
          <span class="min-w-0 truncate text-xs text-slate-300"
            >Strands per phase<HelpTag
              tip="Parallel serpentine paths per phase, stacked across the board width."
            /></span
          >
          <NumberField
            id="strands-per-phase"
            value={config.strands_per_phase}
            min={1}
            max={16}
            step={1}
            integer
            ariaLabel="Strands per phase"
            class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
            onCommit={(value) => (config.strands_per_phase = value)}
          />
        </span>
      </label>
    </div>
    <p class="mt-2 text-[11px] text-slate-500">
      Via diameter: {(config.min_via_drill_mm + 2 * config.min_via_annular_ring_mm).toFixed(3)} mm.
      Trace width and gap set the generator's manufacturing limits.
    </p>
  </div>
</div>
