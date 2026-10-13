<script lang="ts">
  import type { CoilTerminalTool } from "../../utils/coilTerminalTool.svelte";
  import { terminalDescription } from "../../cadTerminals";
  let { tool }: { tool: CoilTerminalTool } = $props();
  const steps = ["Coil", "IN", "OUT", "Review"];
  let stepIndex = $derived(["coil", "input", "output", "review"].indexOf(tool.step ?? ""));
</script>

<section class="shrink-0 border-b border-slate-700 border-l-2 border-l-emerald-400 p-3" aria-label="Set coil terminals">
  <h4 class="text-sm font-semibold text-slate-200">Set coil terminals</h4>
  <ol class="my-3 flex gap-2 text-[11px] text-slate-500" aria-label="Terminal selection steps">
    {#each steps as step, index (step)}
      <li class:text-emerald-300={index === stepIndex} aria-current={index === stepIndex ? "step" : undefined}>{index + 1} {step}</li>
    {/each}
  </ol>
  <p role="status" aria-live="polite" class="mb-3 text-xs leading-relaxed text-slate-200">
    {#if tool.step === "coil"}Choose the coil to configure.
    {:else if tool.step === "input"}Click the IN endpoint for coil {tool.coil}.
    {:else if tool.step === "output"}Click the OUT endpoint for coil {tool.coil}.
    {:else}Review the highlighted IN and OUT points, then choose Done.{/if}
  </p>
  <label class="mb-3 block text-xs text-slate-300">
    Coil
    <select aria-label="Coil for terminal selection" value={tool.coil} onchange={(event) => tool.chooseCoil(event.currentTarget.value)} class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm">
      <option value="" disabled>Choose coil</option>
      {#each tool.coils as coil (coil)}<option value={coil}>{coil}</option>{/each}
    </select>
  </label>
  {#if tool.coil}
    <label class="mb-2 block text-xs text-slate-300">
      Pick on copper layer
      <select aria-label="Copper layer for terminal selection" value={tool.layer} onchange={(event) => tool.chooseLayer(Number(event.currentTarget.value))} class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm">
        {#each tool.layers as layer (layer)}<option value={layer}>Layer {layer}</option>{/each}
      </select>
    </label>
    <p class="mb-3 text-[11px] leading-relaxed text-slate-400">Only this coil's trace endpoints on the chosen layer are selectable. Pan or zoom to separate nearby points.</p>
  {/if}
  <dl class="space-y-2 text-[11px] text-slate-400">
    <div><dt class="font-semibold text-emerald-300">IN</dt><dd>{tool.input ? terminalDescription(tool.input) : "Not selected"}</dd></div>
    <div><dt class="font-semibold text-amber-300">OUT</dt><dd>{tool.output ? terminalDescription(tool.output) : "Not selected"}</dd></div>
  </dl>
  {#if tool.error}<p role="alert" class="mt-3 text-xs text-rose-300">{tool.error}</p>{/if}
  <div class="mt-4 flex flex-wrap justify-between gap-2">
    <button type="button" onclick={tool.cancel} class="rounded border border-slate-700 px-2 py-1.5 text-xs text-slate-400 hover:text-slate-100">Cancel</button>
    {#if tool.step !== "coil"}<button type="button" onclick={tool.back} class="rounded border border-slate-700 px-2 py-1.5 text-xs text-slate-300">Back</button>{/if}
    {#if tool.step === "coil"}
      <button type="button" onclick={tool.next} disabled={!tool.coil} class="rounded border border-emerald-500/50 bg-emerald-500/10 px-2 py-1.5 text-xs text-emerald-300 disabled:opacity-40">Select IN</button>
    {:else}
      <button type="button" onclick={tool.done} disabled={tool.step !== "review"} class="rounded border border-emerald-500/50 bg-emerald-500/10 px-2 py-1.5 text-xs text-emerald-300 disabled:opacity-40">Done</button>
    {/if}
  </div>
</section>
