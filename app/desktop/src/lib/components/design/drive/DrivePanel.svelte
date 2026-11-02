<script lang="ts">
  import type { ConfigStore } from "../../../stores/config.svelte";
  import type { DriveSettings } from "../../../types";
  import NumberField from "../../ui/NumberField.svelte";
  import SettingRow from "../../simulate/SettingRow.svelte";
  import CarriagePanel from "./CarriagePanel.svelte";

  let { config }: { config: ConfigStore } = $props();
  const field = "w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200";
  function update(patch: Partial<DriveSettings>): void {
    config.drive = { ...config.drive, ...patch };
  }
</script>

<section id="drive-targets-heading" aria-label="Drive & force targets" class="space-y-4">
  <fieldset class="space-y-2">
    <legend class="mb-2 text-xs font-semibold text-slate-300">Current &amp; force</legend>
    <SettingRow label="Phase amplitude (A)" help="Selected phase-current amplitude before PWM ripple, not DC supply current."><NumberField id="phase-current" value={config.max_current_a} min={0.01} step={0.05} ariaLabel="Phase current (A)" class={field} onCommit={(v) => (config.max_current_a = v)} /></SettingRow>
    <SettingRow label="Continuous target (N)"><NumberField id="target-force" value={config.target_force_n} min={0.001} step={0.01} ariaLabel="Continuous target force (N)" class={field} onCommit={(v) => (config.target_force_n = v)} /></SettingRow>
    <SettingRow label="Peak target (N)"><NumberField id="peak-force" value={config.peak_force_n} min={0.001} step={0.01} ariaLabel="Peak target force (N)" class={field} onCommit={(v) => (config.peak_force_n = v)} /></SettingRow>
  </fieldset>

  <CarriagePanel {config} />

  <fieldset class="space-y-2 border-t border-slate-700 pt-3">
    <legend class="pr-2 text-xs font-semibold text-slate-300">Operating point</legend>
    <SettingRow label="Bus voltage (V)" help="Motor supply voltage, such as the negotiated USB-PD rail."><NumberField id="bus-voltage" value={config.supply_voltage_v} min={0.1} step={0.5} ariaLabel="Bus voltage (V)" class={field} onCommit={(v) => (config.supply_voltage_v = v)} /></SettingRow>
    <SettingRow label="PWM (kHz)"><NumberField value={config.drive.pwm_hz / 1e3} min={1} step={10} ariaLabel="PWM frequency (kHz)" class={field} onCommit={(v) => update({ pwm_hz: v * 1e3 })} /></SettingRow>
    <SettingRow label="Top speed (m/s)" help="Fastest move at full current. Back-EMF consumes more supply voltage as speed rises." equation={String.raw`E = k_e v`}><NumberField value={config.drive.target_speed_m_s} min={0} step={0.05} ariaLabel="Target speed (m/s)" class={field} onCommit={(v) => update({ target_speed_m_s: v })} /></SettingRow>
    <SettingRow label="Ripple limit (%)" help="Allowed peak-to-peak PWM ripple as a share of phase current." equation={String.raw`r = \frac{\Delta I_{\mathrm{pp}}}{I_{\mathrm{phase}}}\times 100\%`}><NumberField value={Math.round(config.drive.ripple_limit_fraction * 100)} min={1} max={200} step={5} ariaLabel="Ripple limit (% of phase current)" class={field} onCommit={(v) => update({ ripple_limit_fraction: v / 100 })} /></SettingRow>
    <SettingRow label="Usable bus (%)" help="Supply voltage available to the current loop. The remainder leaves control headroom."><NumberField value={Math.round(config.drive.voltage_headroom * 100)} min={10} max={100} step={5} ariaLabel="Usable bus share (%)" class={field} onCommit={(v) => update({ voltage_headroom: v / 100 })} /></SettingRow>
  </fieldset>

  <fieldset class="space-y-2 border-t border-slate-700 pt-3">
    <legend class="pr-2 text-xs font-semibold text-slate-300">Thermal limits</legend>
    <SettingRow label="Winding temp (°C)" help="Copper resistance rises about 0.393% per °C above 20 °C." equation={String.raw`R_T = R_{20}\left[1 + 0.00393\,(T - 20)\right]`}><NumberField value={config.drive.winding_temp_c} min={-40} max={200} step={5} ariaLabel="Winding temperature (°C)" class={field} onCommit={(v) => update({ winding_temp_c: v })} /></SettingRow>
    <SettingRow label="Allowed rise (°C)" help="Temperature rise used for the IPC-2221 trace ampacity."><NumberField value={config.drive.allowed_rise_c} min={1} max={100} step={5} ariaLabel="Allowed trace temperature rise (°C)" class={field} onCommit={(v) => update({ allowed_rise_c: v })} /></SettingRow>
  </fieldset>
</section>
