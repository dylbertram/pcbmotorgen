<script lang="ts">
  import type { ConfigStore } from "../../../stores/config.svelte";
  import { MAGNET_MASS_REFERENCES } from "../../../carriageMass";
  import NumberField from "../../ui/NumberField.svelte";
  import SettingRow from "../../simulate/SettingRow.svelte";

  let { config }: { config: ConfigStore } = $props();
  const field = "w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200";
</script>

<section aria-label="Carriage mass and friction" class="space-y-3 border-t border-slate-700 pt-3">
  <h3 class="text-xs font-semibold text-slate-300">Carriage mass and friction</h3>
  <p class="text-xs leading-relaxed text-slate-400">Use the magnets as a starting estimate, or enter the full moving assembly including its carrier, bushings, enclosure, knob and attached load. Do not include the stationary rail.</p>
  <div class="overflow-x-auto">
    <table class="w-full text-left text-xs text-slate-300" aria-label="Magnet mass breakdown">
      <thead class="text-slate-400"><tr><th class="pb-2 font-normal">Magnets</th><th class="pb-2 text-right font-normal">Each</th><th class="pb-2 text-right font-normal">Total</th></tr></thead>
      <tbody><tr>
        <td class="pr-2">{config.magnet_count} × {config.magnet_width_mm} × {config.magnet_cross_width_mm} × {config.magnet_height_mm} mm {config.magnet_grade}</td>
        <td class="whitespace-nowrap text-right">{config.magnet_mass.massG.toFixed(2)} g</td>
        <td class="whitespace-nowrap pl-2 text-right">{(config.magnet_total_mass_kg * 1000).toFixed(2)} g</td>
      </tr></tbody>
    </table>
  </div>
  <p class="text-xs text-slate-400">{config.magnet_mass.source}. Magnet-only mass excludes the rest of the carriage.</p>
  <label class="flex items-center justify-between gap-2 text-xs text-slate-300">
    Mass basis
    <select aria-label="Carriage mass basis" bind:value={config.carriage_mass_source} class="min-w-0 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400">
      <option value="magnets">Magnet-only default</option>
      <option value="assembly">Full assembly override</option>
    </select>
  </label>
  {#if config.carriage_mass_source === "assembly"}
    <SettingRow label="Full carriage mass (g)" help="Estimated total moving mass. Include the magnets once, plus all other moving parts. A reasonable estimate is enough to start; refine it after prototype testing.">
      <NumberField id="carriage-mass" value={config.carriage_mass_kg * 1000} min={0.001} step={0.1} ariaLabel="Full carriage mass (g)" class={field} onCommit={(v) => (config.carriage_mass_kg = v / 1000)} />
    </SettingRow>
  {:else}
    <p class="text-xs text-emerald-200">Carriage mass: {(config.carriage_mass_kg * 1000).toFixed(2)} g. Updates with magnet size and count.</p>
  {/if}
  <SettingRow label="Bushing / rail friction (N)" help="Estimated sliding resistance between the bushings and rail. Enter force in newtons, not a coefficient of friction. Refine this estimate from prototype tests.">
    <NumberField id="friction-estimate" value={config.friction_n} min={0} step={0.005} ariaLabel="Friction estimate (N)" class={field} onCommit={(v) => (config.friction_n = v)} />
  </SettingRow>
  <details class="text-xs text-slate-400">
    <summary class="cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400">Magnet weight references</summary>
    <ul class="mt-2 space-y-1">
      {#each MAGNET_MASS_REFERENCES as reference (reference.grade + reference.dimensionsMm.join("x"))}
        <li>{reference.dimensionsMm.join(" × ")} mm {reference.grade}: {reference.massG.toFixed(2)} g each. {reference.source}.</li>
      {/each}
    </ul>
    <p class="mt-2">Other sizes use volume × approximate NdFeB density of 7.6 g/cm³. Grade is not treated as an exact density measurement.</p>
  </details>
</section>
