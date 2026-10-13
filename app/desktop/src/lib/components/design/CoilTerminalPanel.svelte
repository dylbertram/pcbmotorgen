<script lang="ts">
  import type { CoilTerminalTool } from "../../utils/coilTerminalTool.svelte";
  import { terminalDescription } from "../../cadTerminals";
  let { tool }: { tool: CoilTerminalTool } = $props();
</script>

<section class="shrink-0 border-b border-slate-700 border-l-2 border-l-emerald-400 p-3" aria-label="Set coil terminals">
  <h4 class="text-sm font-semibold text-slate-200">Set coil terminals</h4>
  <label class="my-3 block text-xs text-slate-300">
    Coil
    <select aria-label="Coil for terminal selection" value={tool.coil} onchange={(event) => tool.chooseCoil(event.currentTarget.value)} class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm">
      <option value="" disabled>Choose coil</option>
      {#each tool.coils as coil (coil)}<option value={coil}>{coil}</option>{/each}
    </select>
  </label>
  <p role="status" aria-live="polite" class="mb-3 text-xs leading-relaxed text-slate-300">
    {#if !tool.coil}No trace endpoints available.
    {:else if tool.step === "input"}Choose IN in the preview.
    {:else if tool.step === "output"}Choose OUT in the preview.
    {:else if tool.defaultKind === "open"}Open ends selected. Flip or change either point if needed.
    {:else if tool.defaultKind === "saved"}Saved endpoints selected.
    {:else}Review IN and OUT, then apply.{/if}
  </p>
  {#if tool.coil}
    <dl class="space-y-3 text-[11px] text-slate-400">
      <div>
        <dt class="flex items-center justify-between gap-2"><span class="font-semibold text-emerald-300">IN</span><button type="button" onclick={() => tool.change("input")} aria-pressed={tool.step === "input"} title="Choose a different IN endpoint in the preview." class="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300">Change IN</button></dt>
        <dd class="mt-1">{tool.input ? terminalDescription(tool.input) : "Not selected"}</dd>
      </div>
      <div>
        <dt class="flex items-center justify-between gap-2"><span class="font-semibold text-amber-300">OUT</span><button type="button" onclick={() => tool.change("output")} aria-pressed={tool.step === "output"} title="Choose a different OUT endpoint in the preview." class="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300">Change OUT</button></dt>
        <dd class="mt-1">{tool.output ? terminalDescription(tool.output) : "Not selected"}</dd>
      </div>
    </dl>
    <button type="button" onclick={tool.flip} disabled={!tool.input || !tool.output} title="Swap IN and OUT without choosing the points again." class="mt-3 rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 disabled:opacity-40">Flip</button>
    {#if tool.step === "input" || tool.step === "output"}
      <label class="mt-3 block text-xs text-slate-300">
        Copper layer
        <select aria-label="Copper layer for terminal selection" value={tool.layer} onchange={(event) => tool.chooseLayer(Number(event.currentTarget.value))} title="Show selectable endpoints on this copper layer." class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm">
          {#each tool.layers as layer (layer)}<option value={layer}>Layer {layer}</option>{/each}
        </select>
      </label>
      {#if tool.input && tool.output}<button type="button" onclick={tool.finishPicking} class="mt-2 text-xs text-slate-400">Keep current points</button>{:else if !tool.defaultKind}<p class="mt-2 text-[11px] text-slate-500">No clear pair of open ends. Choose both points.</p>{/if}
    {/if}
  {/if}
  {#if tool.error}<p role="alert" class="mt-3 text-xs text-rose-300">{tool.error}</p>{/if}
  <div class="mt-4 flex flex-wrap gap-2">
    <button type="button" onclick={tool.done} disabled={!tool.canApply} class="rounded border border-emerald-500/50 bg-emerald-500/10 px-2 py-1.5 text-xs text-emerald-300 disabled:opacity-40">Apply terminals</button>
    {#if tool.nextCoil}<button type="button" onclick={tool.applyAndNext} disabled={!tool.canApply} title="Apply these terminals and review the next coil." class="rounded border border-slate-700 px-2 py-1.5 text-xs text-slate-300 disabled:opacity-40">Apply &amp; next</button>{/if}
    <button type="button" onclick={tool.cancel} class="rounded px-2 py-1.5 text-xs text-slate-400 hover:text-slate-100">Cancel</button>
  </div>
</section>
