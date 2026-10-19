<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { DriveSettings } from "../../types";
  import NumberField from "../ui/NumberField.svelte";
  import Separator from "../ui/Separator.svelte";
  import SettingRow from "./SettingRow.svelte";
  import DriverSelector from "./DriverSelector.svelte";
  import seriesInductorSvg from "../../assets/series-inductor.svg";

  let { config }: { config: ConfigStore } = $props();

  const COPPER_WEIGHTS = [0.5, 1, 2, 3];

  function update(patch: Partial<DriveSettings>): void {
    config.drive = { ...config.drive, ...patch };
  }

  const field = "w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200";
  const selectClass =
    "w-24 shrink-0 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400";
</script>


<section aria-labelledby="driver-settings-heading" class="overflow-hidden rounded-md border border-slate-700 bg-slate-800/30">
  <div class="flex items-center justify-between gap-3 px-3 py-2">
    <h3 id="driver-settings-heading" class="text-sm font-semibold text-slate-200">Driver</h3>
  </div>
  <div class="px-3 pb-3">
    <DriverSelector {config} />
  </div>

  <Separator />

  <div class="space-y-3 px-3 pb-3 pt-2.5">
    <fieldset class="space-y-2">
      <legend class="mb-1.5 text-[11px] text-slate-400">Operating point</legend>
      <div class="grid gap-y-2">
        <SettingRow label="Bus voltage (V)" help="Motor supply voltage, such as the negotiated USB-PD rail."><NumberField id="bus-voltage" value={config.supply_voltage_v} min={0.1} step={0.5} ariaLabel="Bus voltage (V)" class={field} onCommit={(v) => (config.supply_voltage_v = v)} /></SettingRow>
        <SettingRow label="PWM (kHz)"><NumberField value={config.drive.pwm_hz / 1e3} min={1} step={10} ariaLabel="PWM frequency (kHz)" class={field} onCommit={(v) => update({ pwm_hz: v * 1e3 })} /></SettingRow>
        <SettingRow label="Top speed (m/s)" help="Fastest move at full current. Back-EMF consumes more supply voltage as speed rises." equation={String.raw`E = k_e v`}><NumberField value={config.drive.target_speed_m_s} min={0} step={0.05} ariaLabel="Target speed (m/s)" class={field} onCommit={(v) => update({ target_speed_m_s: v })} /></SettingRow>
        <SettingRow label="Ripple limit (%)" help="Allowed peak-to-peak PWM ripple as a share of phase current." equation={String.raw`r = \frac{\Delta I_{\mathrm{pp}}}{I_{\mathrm{phase}}}\times 100\%`}><NumberField value={Math.round(config.drive.ripple_limit_fraction * 100)} min={1} max={200} step={5} ariaLabel="Ripple limit (% of phase current)" class={field} onCommit={(v) => update({ ripple_limit_fraction: v / 100 })} /></SettingRow>
        <SettingRow label="Usable bus (%)" help="Supply voltage available to the current loop. The remainder leaves control headroom."><NumberField value={Math.round(config.drive.voltage_headroom * 100)} min={10} max={100} step={5} ariaLabel="Usable bus share (%)" class={field} onCommit={(v) => update({ voltage_headroom: v / 100 })} /></SettingRow>
        <SettingRow label="Series inductor (µH)" help="External inductance per phase. Reduces PWM current ripple but needs more voltage at speed. Use 0 for none." equation={String.raw`V_L = L\frac{\mathrm{d}i}{\mathrm{d}t}`} image={seriesInductorSvg} imageAlt="One external series inductor between each driver output and PCB winding."><NumberField value={config.drive.series_inductance_h * 1e6} min={0} step={1} ariaLabel="Series inductor per phase (µH)" class={field} onCommit={(v) => update({ series_inductance_h: v * 1e-6 })} /></SettingRow>
      </div>
    </fieldset>

    <Separator />

    <fieldset class="space-y-2">
      <legend class="mb-1.5 text-[11px] text-slate-400">Copper</legend>
      <div class="grid gap-y-2">
        <SettingRow label="Outer layers" help="Finished copper weight. 1 oz ≈ 35 µm, 2 oz ≈ 70 µm.">
          <select aria-label="Outer layer copper weight" value={String(config.drive.outer_copper_oz)} onchange={(e) => update({ outer_copper_oz: Number(e.currentTarget.value) })} class={selectClass}>
            {#each COPPER_WEIGHTS as oz (oz)}<option value={String(oz)}>{oz} oz</option>{/each}
          </select>
        </SettingRow>
        <SettingRow label="Inner layers">
          <select aria-label="Inner layer copper weight" value={String(config.drive.inner_copper_oz)} onchange={(e) => update({ inner_copper_oz: Number(e.currentTarget.value) })} class={selectClass}>
            {#each COPPER_WEIGHTS as oz (oz)}<option value={String(oz)}>{oz} oz</option>{/each}
          </select>
        </SettingRow>
        <SettingRow label="Winding temp (°C)" help="Copper resistance rises about 0.393% per °C above 20 °C." equation={String.raw`R_T = R_{20}\left[1 + 0.00393\,(T - 20)\right]`}><NumberField value={config.drive.winding_temp_c} min={-40} max={200} step={5} ariaLabel="Winding temperature (°C)" class={field} onCommit={(v) => update({ winding_temp_c: v })} /></SettingRow>
        <SettingRow label="Allowed rise (°C)" help="Temperature rise used for the IPC-2221 trace ampacity."><NumberField value={config.drive.allowed_rise_c} min={1} max={100} step={5} ariaLabel="Allowed trace temperature rise (°C)" class={field} onCommit={(v) => update({ allowed_rise_c: v })} /></SettingRow>
        <SettingRow label="Via plating (µm)" help="Barrel plating thickness. 25 µm is the IPC class 2 minimum average."><NumberField value={Math.round(config.drive.via_plating_m * 1e6)} min={5} max={100} step={5} ariaLabel="Via plating thickness (µm)" class={field} onCommit={(v) => update({ via_plating_m: v * 1e-6 })} /></SettingRow>
      </div>
    </fieldset>
  </div>
</section>
