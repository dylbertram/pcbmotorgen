<script lang="ts">
  /**
   * MoverPositionControls.svelte — shared mover-position controls for the
   * MotionStore: position number field and the travel slider, plus the live
   * readout. Motion input is continuous — a coreless motor has no
   * detent/cogging force. The slider endpoints come from the backend travel
   * envelope (the simulation crate's `travel_envelope_charge_based`, kata
   * k5r5): the charge-based electromagnetic rests clamped into the
   * span-aware flush limits, so the array edges sit at most on the copper
   * active-area bounds at min and max, and the endpoints are limits, not
   * stable rest positions —
   * the rests (spaced one electrical period P_e) are marked by the
   * force-chart zeros below, and the mover may hold position between them.
   * While only the placeholder envelope is active (backend unavailable /
   * not yet fetched) the endpoints are a fixed reference pin and the
   * store's `envelopeWarning` is rendered below — never silent (kata ab30).
   *
   * Used by the Design reflection (TravelDiagram) and the CoilPreview
   * lightbox so both screens expose identical position controls on the same
   * shared store.
   */
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { MotionStore } from "../../stores/motion.svelte";
  import { stripBoundsDomainMm } from "../../previewGeometry";
  import NumberField from "../ui/NumberField.svelte";
  import Slider from "../ui/Slider.svelte";
  import HoldingForceChart from "./HoldingForceChart.svelte";

  let { config, motion, showWaveform = true }: { config: ConfigStore; motion: MotionStore; showWaveform?: boolean } =
    $props();

  // Strip extent in the DOMAIN (routing) frame — exactly what the coil
  // canvas overlay and the iso view draw, so the printed numbers always
  // match the picture.
  let bounds = $derived(stripBoundsDomainMm(config, motion));
  const travelRangeMm = $derived(motion.moverMaxMm - motion.moverMinMm);
</script>

<div class="mt-3" aria-label="Mover position">
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
      class="w-24 rounded px-1.5 py-0.5 text-right font-mono text-emerald-300"
      onCommit={(value) => motion.commit(value)}
    />
    <span class="text-xs text-slate-400">mm</span>
  </div>

  <!-- Bits UI slider (accessible role="slider" thumb): Arrow/Home/End keys
       and pointer drag commit continuously into the MotionStore; the
       endpoints are the backend travel envelope above. -->
  <Slider
    class="mt-2"
    min={motion.moverMinMm}
    max={motion.moverMaxMm}
    step={0.1}
    value={motion.clampedPositionMm}
    ariaLabel="Mover position slider (mm)"
    onValueChange={(v) => motion.commit(v)}
  />

  <!-- Normalized per-phase holding force vs position (3 waves at 120° for
       a 3-phase motor); phase-A zeros mark the stable rest positions. -->
  {#if showWaveform}<HoldingForceChart {config} {motion} />{/if}

  <div class="mt-1 text-[10px] text-slate-500" aria-live="polite">
    Position: {motion.clampedPositionMm.toFixed(1)} mm · Mover extent:
    <span class="text-slate-300">{bounds.startMm.toFixed(1)} - {bounds.endMm.toFixed(1)} mm</span>
    · Offset from rest: {motion.offsetFromRestMm.toFixed(1)} / {travelRangeMm.toFixed(1)} mm
  </div>

  {#if motion.envelopeWarning}
    <!-- Placeholder travel envelope in effect (kata ab30): the bounds are a
         fixed reference pin, NOT backend physics — say so, loudly. -->
    <p class="mt-1 text-[10px] text-amber-400" role="status">
      {motion.envelopeWarning.message}
    </p>
  {/if}
</div>
