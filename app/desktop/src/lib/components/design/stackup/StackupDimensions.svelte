<script lang="ts">
  import type { ConfigStore } from "../../../stores/config.svelte";
  import NumberField from "../../ui/NumberField.svelte";
  import HelpTag from "../../ui/HelpTag.svelte";
  import TravelStackupView from "./TravelStackupView.svelte";

  let { config }: { config: ConfigStore } = $props();
  const fieldClass = "w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200";
</script>

<div class="stackup-fields mb-2 grid items-center gap-3">
  <div class="space-y-2.5">
    <label class="flex items-center justify-between gap-2 text-xs text-slate-300">
      <span>Air gap (mm)<HelpTag label="About air gap" tip="Clearance from the top of the PCB to the magnets. A smaller gap increases field strength." /></span>
      <NumberField id="air-gap" value={config.air_gap_mm} min={0} step={0.05} ariaLabel="Air gap (mm)" class={fieldClass} onCommit={(value) => (config.air_gap_mm = value)} />
    </label>
    <label class="flex items-center justify-between gap-2 text-xs text-slate-300">
      <span>PCB thickness (mm)</span>
      {#if config.pcb_stackup_mm}
        <output aria-label="PCB thickness (mm)" class="font-mono text-emerald-200">{Number(config.pcb_thickness_mm.toPrecision(6))} mm</output>
      {:else}
        <NumberField id="pcb-thickness" value={config.pcb_thickness_mm} min={0.1} step={0.1} ariaLabel="PCB thickness (mm)" class={fieldClass} onCommit={(value) => (config.pcb_thickness_mm = value)} />
      {/if}
    </label>
  </div>
  <div class="mx-auto w-full max-w-[160px]"><TravelStackupView {config} /></div>
</div>

<style>
  @container (min-width: 560px) {
    .stackup-fields { grid-template-columns: minmax(0, 1fr) 160px; }
  }
</style>
