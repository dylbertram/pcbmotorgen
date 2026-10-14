<script lang="ts">
  import type { CadGeometry } from "../../types";
  import { PHASE_LABELS, coilNames, phaseOf, unmappedCoils, withCoilPhase } from "../../cadPhases";

  /**
   * Assign each imported coil to a motor phase. KiCad export, DRC, and the
   * Simulation tab read the imported copper through this mapping.
   */
  let {
    geometry,
    phases,
    onChange,
  }: {
    geometry: CadGeometry;
    /** Phase count of the design; limits the offered labels. */
    phases: number;
    onChange: (geometry: CadGeometry) => void;
  } = $props();

  let coils = $derived(coilNames(geometry));
  let labels = $derived(PHASE_LABELS.slice(0, Math.max(1, phases)));
  let missing = $derived(unmappedCoils(geometry));

  // Count coils per phase so parallel groups are visible.
  let groupSize = $derived.by(() => {
    const counts: Record<string, number> = {};
    for (const coil of coils) {
      const p = phaseOf(geometry, coil);
      if (p) counts[p] = (counts[p] ?? 0) + 1;
    }
    return counts;
  });
</script>

<section aria-labelledby="coil-phase-heading" class="rounded-md border border-slate-700 bg-slate-800/30 px-3 py-2.5">
  <div class="flex items-baseline justify-between gap-3">
    <h3 id="coil-phase-heading" class="text-xs font-semibold text-slate-200">Imported coil phases</h3>
    {#if missing.length}
      <span class="text-xs text-amber-300">{missing.length} unassigned</span>
    {:else}
      <span class="text-xs text-emerald-300">All coils assigned</span>
    {/if}
  </div>
  <p class="mt-1 text-xs text-slate-400">
    Each coil becomes part of its phase's net. Coils that share a phase are driven in parallel.
  </p>
  <ul class="mt-2 space-y-1.5">
    {#each coils as coil (coil)}
      {@const phase = phaseOf(geometry, coil)}
      {@const terminals = geometry.coil_terminals?.[coil]}
      <li class="flex items-center justify-between gap-3">
        <span class="min-w-0 truncate text-xs text-slate-200" title={coil}>
          {coil}
          <span class="text-slate-500">· {terminals ? "IN/OUT picked" : "ends inferred"}</span>
        </span>
        <select
          aria-label={`Phase for coil ${coil}`}
          value={phase ?? ""}
          onchange={(e) => onChange(withCoilPhase(geometry, coil, e.currentTarget.value || null))}
          class="w-28 shrink-0 rounded border px-2 py-1 text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400 {phase ? 'border-slate-700 bg-slate-900 text-slate-100' : 'border-amber-500/60 bg-amber-500/10 text-amber-100'}"
        >
          <option value="">Choose phase</option>
          {#each labels as label (label)}
            <option value={label}>
              Phase {label}{groupSize[label] > 1 && phase === label ? ` (${groupSize[label]} coils)` : ""}
            </option>
          {/each}
        </select>
      </li>
    {/each}
  </ul>
</section>
