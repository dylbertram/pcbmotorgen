<script lang="ts">
  import type { CadGeometry } from "../../types";
  import { PHASE_LABELS, phaseOf, withCoilPhase } from "../../cad/cadPhases";

  let { geometry, sourceLayerCoils, coils, coilType, phases, busy, onAssignSourceLayer, onGeometryChange }: {
    geometry: CadGeometry;
    sourceLayerCoils: Record<string, string>;
    coils: string[];
    coilType: "motor" | "sensor";
    phases: number;
    busy: boolean;
    onAssignSourceLayer: (name: string, coil: string) => void;
    onGeometryChange: (geometry: CadGeometry) => void;
  } = $props();
</script>

<section class="border-t border-slate-700 pt-3" aria-label="Source layer coil assignments">
  <h3 class="text-xs font-medium text-slate-100" title="Source layers with the same coil name belong together. Copper layers come from Z heights.">Source coils</h3>
  <div class="mt-3 grid gap-2">
    {#each Object.entries(geometry.source_layer_coils ?? {}) as [name, coil] (name)}
      <label class="flex items-center justify-between gap-3 text-xs text-slate-300">
        <span class="min-w-0 break-all font-mono">{name}</span>
        <input aria-label={`Coil for source layer ${name}`} value={Object.hasOwn(sourceLayerCoils, name) ? sourceLayerCoils[name] : coil} oninput={(event) => onAssignSourceLayer(name, event.currentTarget.value)} disabled={busy} class="w-28 shrink-0 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100" />
      </label>
    {/each}
  </div>
  {#if Object.values(sourceLayerCoils).some((coil) => !coil.trim())}
    <p role="alert" class="mt-2 text-xs text-rose-200">Enter a coil name for every source layer assignment.</p>
  {/if}
</section>
{#if coilType === "motor"}
  <section class="border-t border-slate-700 pt-3" aria-label="Motor phase assignments">
    <h3 class="text-xs font-medium text-slate-100">Motor phases</h3>
    <p class="mt-2 text-xs text-slate-400">Choose the motor phase for each coil. Coils on the same phase are driven in parallel.</p>
    <div class="mt-3 grid gap-2">
      {#each coils as coil (coil)}
        <label class="flex items-center justify-between gap-3 text-xs text-slate-300">
          <span class="min-w-0 truncate">{coil}</span>
          <select aria-label={`Phase for coil ${coil}`} value={phaseOf(geometry, coil) ?? ""} disabled={busy}
            onchange={(event) => onGeometryChange(withCoilPhase(geometry, coil, event.currentTarget.value || null))}
            class="w-28 shrink-0 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100">
            <option value="">Choose phase</option>
            {#each PHASE_LABELS.slice(0, phases) as phase (phase)}<option value={phase}>Phase {phase}</option>{/each}
          </select>
        </label>
      {/each}
    </div>
  </section>
{/if}
