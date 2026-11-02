<script lang="ts">
  /** The slider uses travel limits, which need not be stable rest positions. */
  import type { MotionStore } from "../../stores/motion.svelte";
  import NumberField from "../ui/NumberField.svelte";
  import Slider from "../ui/Slider.svelte";
  import HelpTag from "../ui/HelpTag.svelte";
  let { motion }: { motion: MotionStore } = $props();
</script>

<div aria-label="Mover position">
  <div class="flex items-center gap-2">
    <label
      for="mover-position-value"
      class="text-xs text-slate-400 whitespace-nowrap"
    >
      Position:
    </label>
    <NumberField
      id="mover-position-value"
      min={motion.moverMinMm}
      max={motion.moverMaxMm}
      step={0.1}
      value={motion.clampedPositionMm}
      ariaLabel="Mover position (mm)"
      class="w-16 rounded px-1.5 py-0.5 text-right font-mono text-emerald-300"
      onCommit={(value) => motion.commit(value)}
    />
    <span class="text-xs text-slate-400">mm</span>
    <div class="min-w-0 flex-1">
      <Slider
        min={motion.moverMinMm}
        max={motion.moverMaxMm}
        step={0.1}
        value={motion.clampedPositionMm}
        ariaLabel="Mover position slider (mm)"
        onValueChange={(v) => motion.commit(v)}
      />
    </div>
  </div>

  {#if motion.envelopeWarning}
    <!-- Placeholder travel envelope in effect (kata ab30): the bounds are a
         fixed reference pin, NOT backend physics — say so, loudly. -->
    <p class="mt-1 text-[10px] text-amber-400" role="status">
      Travel limits are estimated. Simulation backend unavailable.
      <HelpTag label="About estimated travel limits" tip="The slider uses placeholder limits, not calculated electromagnetic limits. Run the desktop app for simulated travel." />
    </p>
  {/if}
</div>
