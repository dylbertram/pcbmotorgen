<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import { initialPcbStackup, validatePcbStackup, pcbStackupHeightsMm } from "../../pcbStackup";
  import NumberField from "../ui/NumberField.svelte";
  let { config }: { config: ConfigStore } = $props();
  let error = $state("");
  const stack = $derived(config.pcb_stackup_mm);
  const validation = $derived.by(() => {
    if (!stack) return "";
    try { validatePcbStackup(stack, config.num_layers); return ""; } catch (e) { return String(e instanceof Error ? e.message : e); }
  });
  const heights = $derived(stack && !validation ? pcbStackupHeightsMm(stack) : []);
  function enable() {
    try { config.pcb_stackup_mm = initialPcbStackup(config.num_layers, config.pcb_thickness_mm, config.drive.outer_copper_oz, config.drive.inner_copper_oz); error = ""; }
    catch { error = "PCB thickness must exceed the combined copper thickness. Increase the total thickness or reduce copper weight first."; }
  }
  function disable() {
    const total = config.pcb_thickness_mm;
    config.pcb_stackup_mm = null; config.pcb_thickness_mm = total; error = "";
  }
  function change(kind: "copper_mm" | "dielectric_mm", index: number, value: number) {
    if (!stack) return;
    config.pcb_stackup_mm = { ...stack, [kind]: stack[kind].map((old, i) => i === index ? value : old) };
  }
</script>

<fieldset class="my-3 space-y-2 border-t border-slate-700 pt-3">
  <legend class="text-xs font-medium text-slate-300">PCB layers</legend>
  <label class="flex items-center gap-2 text-xs text-slate-300"><input type="checkbox" class="accent-emerald-500" checked={!!stack} onchange={() => stack ? disable() : enable()} />Define each layer thickness</label>
  {#if stack}
    <p class="text-[11px] leading-relaxed text-slate-400">Layer 1 is at the top. Copper and dielectric thicknesses add up to the PCB total. This replaces imported Z placement. Solder mask is separate.</p>
    {#if validation}
      <p role="alert" class="text-xs text-amber-300">{validation}</p>
      <button type="button" class="rounded border border-slate-600 px-2 py-1 text-xs text-slate-200" onclick={enable}>Reset for {config.num_layers} layers</button>
    {:else}
      <ol aria-label="PCB stackup from top to bottom" class="space-y-1">
        {#each stack.copper_mm as thickness, i (i)}
          <li class="space-y-1">
            <label class="flex items-center justify-between gap-2 text-xs text-slate-300"><span>Layer {i + 1} copper (µm)<span class="block text-[10px] text-slate-500">Center {heights[i].toFixed(4)} mm</span></span>
              <NumberField value={thickness * 1000} min={1} step={1} ariaLabel={`Layer ${i + 1} copper thickness (µm)`} class="w-24 px-2 py-1 text-xs font-mono" onCommit={value => change("copper_mm", i, value / 1000)} />
            </label>
            {#if i < stack.dielectric_mm.length}
              <label class="flex items-center justify-between gap-2 border-l border-slate-700 pl-3 text-xs text-slate-400"><span>Dielectric {i + 1} (mm)</span>
                <NumberField value={stack.dielectric_mm[i]} min={.001} step={.01} ariaLabel={`Dielectric ${i + 1} thickness (mm)`} class="w-24 px-2 py-1 text-xs font-mono" onCommit={value => change("dielectric_mm", i, value)} />
              </label>
            {/if}
          </li>
        {/each}
      </ol>
    {/if}
  {/if}
  {#if error}<p role="alert" class="text-xs text-amber-300">{error}</p>{/if}
</fieldset>
