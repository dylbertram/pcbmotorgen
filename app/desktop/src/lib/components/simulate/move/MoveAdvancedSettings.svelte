<script lang="ts">
  import type { MoveFormInput } from "../../../move/moveForm";

  let { form = $bindable(), savedCustomLoss, onOpenFieldSettings }: {
    form: MoveFormInput;
    savedCustomLoss: boolean;
    onOpenFieldSettings?: () => void;
  } = $props();
</script>

<details class="text-xs text-slate-400">
  <summary class="cursor-pointer text-slate-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">Advanced move settings</summary>
  <div class="mt-2 grid gap-2 sm:grid-cols-2">
    <label class="flex items-center justify-between gap-2">Start speed
      <span><input type="number" step="0.01" aria-label="Start speed in metres per second" bind:value={form.advanced.initialVelocityMPerS} class="w-20 rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-slate-100" /> m/s</span>
    </label>
    <label class="flex items-center justify-between gap-2">End speed
      <span><input type="number" step="0.01" aria-label="End speed in metres per second" bind:value={form.advanced.finalVelocityMPerS} class="w-20 rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-slate-100" /> m/s</span>
    </label>
    <label class="flex items-center justify-between gap-2">Damping
      <span><input type="number" step="0.01" min="0" aria-label="Viscous damping" bind:value={form.advanced.dampingNsPerM} class="w-20 rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-slate-100" /> N·s/m</span>
    </label>
    <label class="flex items-center justify-between gap-2">Added load
      <span><input type="number" step="0.01" aria-label="Signed external load" bind:value={form.advanced.externalLoadN} class="w-20 rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-slate-100" /> N</span>
    </label>
    <label class="flex items-center justify-between gap-2">Electrical reference
      <span><input type="number" step="0.0001" aria-label="Controller electrical reference in radians" bind:value={form.advanced.electricalAngleRad} class="w-24 rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-slate-100" /> rad</span>
    </label>
    <label class="flex items-center justify-between gap-2">Force-map positions
      <input type="number" step="1" min="2" max="513" aria-label="Force-map positions" bind:value={form.advanced.forcePositions} class="w-20 rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-slate-100" />
    </label>
    <label class="flex items-center justify-between gap-2">Time step
      <span><input type="number" step="0.00001" min="0.00001" aria-label="Time step in seconds" placeholder="auto"
        value={form.advanced.timeStepS ?? ""} oninput={(e) => { const v = e.currentTarget.value; form.advanced.timeStepS = v === "" ? null : Number(v); }}
        class="w-24 rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-slate-100" /> s</span>
    </label>
    <label class="flex items-center gap-2">
      <input type="checkbox" bind:checked={form.advanced.acceptsRegeneration} class="accent-emerald-400" />
      Supply can absorb returned energy
    </label>
  </div>
  <p class="mt-2 text-slate-500">Positions are measured from the start of travel. The electrical reference belongs to the controller, not the design; change it only if you know the winding polarity.</p>
  {#if savedCustomLoss}
    <p class="mt-2 text-amber-300">This saved move has its own loss declaration. Calculate replaces it with the current engineering estimate. Export data first if you need the old declaration.</p>
  {/if}
  {#if onOpenFieldSettings}<button type="button" onclick={onOpenFieldSettings} class="mt-2 text-sky-300 underline-offset-2 hover:underline">Field and loss settings</button>{/if}
</details>
