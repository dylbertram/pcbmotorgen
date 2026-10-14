<script lang="ts">
  import type { CadGeometry } from "../../types";
  import type { CoilTerminalTool } from "../../utils/coilTerminalTool.svelte";
  import { assignCadTerminals, terminalDescription } from "../../cadTerminals";
  let { geometry, tool, onEdit, onGeometryChange }: {
    geometry: CadGeometry;
    tool?: CoilTerminalTool;
    onEdit?: (coil: string) => void;
    onGeometryChange?: (geometry: CadGeometry) => void;
  } = $props();
</script>

{#if Object.keys(geometry.coil_terminals ?? {}).length}
  <section class="shrink-0 border-t border-slate-700 pt-3" aria-label="Configured coil terminals">
    <h4 class="mb-2 text-xs font-semibold text-slate-300">Coil terminals</h4>
    <div class="flex flex-wrap gap-4">
      {#each Object.entries(geometry.coil_terminals ?? {}) as [coil, terminals] (coil)}
        <div class="space-y-1 text-[11px] text-slate-400">
          <p class="font-semibold text-slate-200">Coil {coil}</p>
          <p>IN {terminalDescription(terminals.input)}</p>
          <p>OUT {terminalDescription(terminals.output)}</p>
          <div class="flex gap-3">
            {#if onEdit}<button type="button" disabled={tool?.active} onclick={() => onEdit?.(coil)} class="text-xs text-emerald-300 disabled:opacity-40" aria-label={`Edit coil ${coil} terminals`}>Edit terminals</button>{/if}
            {#if onGeometryChange}<button type="button" disabled={tool?.active} onclick={() => onGeometryChange?.(assignCadTerminals(geometry, coil, { input: terminals.output, output: terminals.input }))} class="text-xs text-emerald-300 disabled:opacity-40" aria-label={`Flip coil ${coil} terminals`} title="Swap this coil's IN and OUT terminals.">Flip</button>{/if}
          </div>
        </div>
      {/each}
    </div>
  </section>
{/if}
