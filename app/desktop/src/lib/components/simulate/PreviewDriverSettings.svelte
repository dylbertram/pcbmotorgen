<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import DriverSelector from "./DriverSelector.svelte";
  import HelpTag from "../ui/HelpTag.svelte";
  import NumberField from "../ui/NumberField.svelte";
  import seriesInductorSvg from "../../assets/series-inductor.svg";

  let { config, onOpenDriverCalculator }: {
    config: ConfigStore;
    onOpenDriverCalculator?: () => void;
  } = $props();
</script>

<fieldset class="space-y-2">
  <legend class="text-xs font-semibold text-slate-200">Driver inductor</legend>
  <label class="flex items-center justify-between gap-2 text-xs text-slate-300">
    <span>Per phase (µH)<HelpTag label="About series inductance" tip="One external inductor per driver output. Applies to every phase; 0 means none. Not part of PCB geometry." equation={String.raw`V_L = L\frac{\mathrm{d}i}{\mathrm{d}t}`} image={seriesInductorSvg} imageAlt="Each driver output connects through an added inductor to a PCB winding." /></span>
    <NumberField value={config.drive.series_inductance_h * 1e6} min={0} step={1}
      ariaLabel="Series inductor per phase (µH)" class="w-20 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
      onCommit={(v) => { config.drive = { ...config.drive, series_inductance_h: v * 1e-6 }; }} />
  </label>
  <p class="text-[11px] text-slate-400">Adding inductance can reduce PWM current ripple, but needs more voltage at speed.</p>
</fieldset>
<div class="mt-4 border-t border-slate-700 pt-3"><DriverSelector {config} /></div>
<div class="mt-4 space-y-2 border-t border-slate-700 pt-3">
  <p class="text-xs text-slate-400">These are the motor's saved drive assumptions. Compare other drivers independently in the calculator.</p>
  <button type="button" onclick={onOpenDriverCalculator} disabled={!onOpenDriverCalculator} class="text-xs text-sky-300 hover:underline disabled:opacity-40">Open driver calculator</button>
</div>
