<script lang="ts">
  import type { ConfigStore } from "../../../stores/config.svelte";
  import MagnetGradeHelper from "../MagnetGradeHelper.svelte";
  import NumberField from "../../ui/NumberField.svelte";
  import HelpTag from "../../ui/HelpTag.svelte";
  import Separator from "../../ui/Separator.svelte";

  let { config }: { config: ConfigStore } = $props();
</script>

<section aria-labelledby="magnets-heading" class="overflow-hidden rounded-md border border-slate-700 bg-slate-800/30">
  <header class="px-3 py-2">
    <h3 id="magnets-heading" class="text-sm font-semibold text-slate-200">Magnets</h3>
  </header>

  <Separator />

  <div class="px-3 pb-3 pt-2.5">
    <div class="grid gap-x-3 gap-y-2.5 sm:grid-cols-2">
      <label class="min-w-0">
        <span class="flex items-center justify-between gap-2">
          <span class="min-w-0 truncate text-xs text-slate-300">Magnet count</span>
          <NumberField
            id="magnet-count"
            value={config.magnet_count}
            min={2}
            max={64}
            step={1}
            integer
            ariaLabel="Magnet count"
            class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
            onCommit={(value) => (config.magnet_count = value)}
          />
        </span>
      </label>

      <label class="min-w-0">
        <span class="flex items-center justify-between gap-2">
          <span class="min-w-0 truncate text-xs text-slate-300"
            >X length (mm)<HelpTag label="About X Length" tip="Magnet length along travel. The default fill factor is 0.75; higher values leave less gap." equation={String.raw`k = \frac{W_m}{\tau_p},\qquad g_m = \tau_p - W_m`} /></span
          >
          <NumberField
            id="magnet-width"
            value={config.magnet_width_mm}
            min={0.5 * config.pole_pitch_mm}
            max={1.0 * config.pole_pitch_mm}
            step={0.1}
            ariaLabel="X Length (mm), magnet length along the travel axis"
            class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
            onCommit={(value) => (config.magnet_width_mm = value)}
          />
        </span>
        {#if config.magnet_width_mm / config.pole_pitch_mm > 0.85}
          <span
            class="mt-1 block text-[10px] text-amber-400"
            role="status"
            aria-live="polite"
          >
            Flux leakage between adjacent magnets.
          </span>
        {/if}
      </label>

      <label class="min-w-0">
        <span class="flex items-center justify-between gap-2">
          <span class="min-w-0 truncate text-xs text-slate-300"
            >Y width (mm)<HelpTag label="About magnet width" tip="Width across the stator. Sets the active conductor length." /></span
          >
          <NumberField
            id="magnet-cross-width"
            value={config.magnet_cross_width_mm}
            min={0.1}
            max={40}
            step={0.1}
            ariaLabel="Y Width (mm), magnet width across the stator"
            class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
            onCommit={(value) => (config.magnet_cross_width_mm = value)}
          />
        </span>
      </label>

      <label class="min-w-0">
        <span class="flex items-center justify-between gap-2">
          <span class="min-w-0 truncate text-xs text-slate-300"
            >Z thickness (mm)<HelpTag label="About magnet thickness"
              tip="Thickness along magnetisation. For a coreless motor, aim for at least {(config.pole_pitch_mm * 0.5).toFixed(1)} mm."
              equation={String.raw`h_m \gtrsim \frac{\tau_p}{2}`}
            /></span
          >
          <NumberField
            id="magnet-height"
            value={config.magnet_height_mm}
            min={0.1}
            max={20}
            step={0.1}
            ariaLabel="Z Thickness (mm), magnetisation-axis thickness"
            class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
            onCommit={(value) => (config.magnet_height_mm = value)}
          />
        </span>
      </label>

      <div class="sm:col-span-2">
        <MagnetGradeHelper {config} />
      </div>
    </div>
  </div>
</section>
