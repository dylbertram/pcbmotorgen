<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { DriveSettings, DriverSpec } from "../../types";
  import { DRIVER_PRESETS } from "../../types";
  import NumberField from "../ui/NumberField.svelte";
  import Separator from "../ui/Separator.svelte";
  import SettingRow from "./SettingRow.svelte";

  let { config }: { config: ConfigStore } = $props();

  const COPPER_WEIGHTS = [0.5, 1, 2, 3];

  // A preset is "selected" only while every limit still matches it.
  let presetName = $derived.by(() => {
    const d = config.drive.driver;
    const match = DRIVER_PRESETS.find(
      (p) =>
        p.name === d.name &&
        p.min_supply_v === d.min_supply_v &&
        p.max_supply_v === d.max_supply_v &&
        p.peak_current_a === d.peak_current_a &&
        p.continuous_rms_a === d.continuous_rms_a &&
        p.rds_on_ohm === d.rds_on_ohm &&
        p.max_pwm_hz === d.max_pwm_hz,
    );
    return match ? match.name : "custom";
  });

  function update(patch: Partial<DriveSettings>): void {
    config.drive = { ...config.drive, ...patch };
  }

  function updateDriver(patch: Partial<DriverSpec>): void {
    const driver = { ...config.drive.driver, ...patch };
    // Editing a preset's limits makes it a custom part.
    if (presetName !== "custom" && !("name" in patch)) {
      driver.name = `${config.drive.driver.name} (custom)`;
    }
    update({ driver });
  }

  function choosePreset(name: string): void {
    const preset = DRIVER_PRESETS.find((p) => p.name === name);
    if (preset) update({ driver: { ...preset } });
  }

  const field = "w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200";
  const selectClass =
    "w-24 shrink-0 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400";
</script>


<section aria-labelledby="driver-settings-heading" class="overflow-hidden rounded-md border border-slate-700 bg-slate-800/30">
  <div class="flex items-center justify-between gap-3 px-3 py-2">
    <h3 id="driver-settings-heading" class="text-xs font-semibold uppercase tracking-wider text-slate-200">Driver</h3>
    <select
      aria-label="Driver preset"
      value={presetName}
      onchange={(e) => choosePreset(e.currentTarget.value)}
      class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400"
    >
      {#each DRIVER_PRESETS as preset (preset.name)}
        <option value={preset.name}>{preset.name}</option>
      {/each}
      <option value="custom" disabled={presetName !== "custom"}>Custom</option>
    </select>
  </div>

  <Separator />

  <div class="space-y-3 px-3 pb-3 pt-2.5">
    <fieldset class="space-y-2">
      <legend class="mb-1.5 text-[11px] text-slate-400">Datasheet limits of {config.drive.driver.name}</legend>
      <div class="grid gap-y-2">
        <SettingRow label="Min supply (V)"><NumberField value={config.drive.driver.min_supply_v} min={0} step={0.5} ariaLabel="Driver minimum supply (V)" class={field} onCommit={(v) => updateDriver({ min_supply_v: v })} /></SettingRow>
        <SettingRow label="Max supply (V)"><NumberField value={config.drive.driver.max_supply_v} min={0.1} step={1} ariaLabel="Driver maximum supply (V)" class={field} onCommit={(v) => updateDriver({ max_supply_v: v })} /></SettingRow>
        <SettingRow label="Peak / OCP (A)" help="Overcurrent trip or peak output rating. Phase current plus half the PWM ripple must stay below it."><NumberField value={config.drive.driver.peak_current_a} min={0.01} step={0.1} ariaLabel="Driver peak current (A)" class={field} onCommit={(v) => updateDriver({ peak_current_a: v })} /></SettingRow>
        <SettingRow label="Continuous (A RMS)"><NumberField value={config.drive.driver.continuous_rms_a} min={0.01} step={0.1} ariaLabel="Driver continuous current (A RMS)" class={field} onCommit={(v) => updateDriver({ continuous_rms_a: v })} /></SettingRow>
        <SettingRow label="R_DS(on) HS+LS (mΩ)" help="Total on-resistance in the current path: one high-side plus one low-side FET."><NumberField value={Math.round(config.drive.driver.rds_on_ohm * 1e4) / 10} min={0} step={10} ariaLabel="Driver on-resistance, high plus low side (mΩ)" class={field} onCommit={(v) => updateDriver({ rds_on_ohm: v / 1e3 })} /></SettingRow>
        <SettingRow label="Max PWM (kHz)"><NumberField value={config.drive.driver.max_pwm_hz / 1e3} min={1} step={10} ariaLabel="Driver maximum PWM frequency (kHz)" class={field} onCommit={(v) => updateDriver({ max_pwm_hz: v * 1e3 })} /></SettingRow>
      </div>
    </fieldset>

    <Separator />

    <fieldset class="space-y-2">
      <legend class="mb-1.5 text-[11px] text-slate-400">Operating point</legend>
      <div class="grid gap-y-2">
        <SettingRow label="Bus voltage (V)" help="The motor supply rail, e.g. the negotiated USB-PD voltage."><NumberField id="bus-voltage" value={config.supply_voltage_v} min={0.1} step={0.5} ariaLabel="Bus voltage (V)" class={field} onCommit={(v) => (config.supply_voltage_v = v)} /></SettingRow>
        <SettingRow label="PWM (kHz)"><NumberField value={config.drive.pwm_hz / 1e3} min={1} step={10} ariaLabel="PWM frequency (kHz)" class={field} onCommit={(v) => update({ pwm_hz: v * 1e3 })} /></SettingRow>
        <SettingRow label="Top speed (m/s)" help="Fastest move at full current. Back-EMF grows with speed and eats into the bus voltage."><NumberField value={config.drive.target_speed_m_s} min={0} step={0.05} ariaLabel="Target speed (m/s)" class={field} onCommit={(v) => update({ target_speed_m_s: v })} /></SettingRow>
        <SettingRow label="Ripple limit (%)" help="Allowed peak-to-peak PWM ripple as a share of the phase current."><NumberField value={Math.round(config.drive.ripple_limit_fraction * 100)} min={1} max={200} step={5} ariaLabel="Ripple limit (% of phase current)" class={field} onCommit={(v) => update({ ripple_limit_fraction: v / 100 })} /></SettingRow>
        <SettingRow label="Usable bus (%)" help="Share of the bus the current loop may use, leaving control headroom."><NumberField value={Math.round(config.drive.voltage_headroom * 100)} min={10} max={100} step={5} ariaLabel="Usable bus share (%)" class={field} onCommit={(v) => update({ voltage_headroom: v / 100 })} /></SettingRow>
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
        <SettingRow label="Winding temp (°C)" help="Copper resistance rises 0.393 %/K. 75 °C is a typical worst case."><NumberField value={config.drive.winding_temp_c} min={-40} max={200} step={5} ariaLabel="Winding temperature (°C)" class={field} onCommit={(v) => update({ winding_temp_c: v })} /></SettingRow>
        <SettingRow label="Allowed rise (°C)" help="Temperature rise used for the IPC-2221 trace ampacity."><NumberField value={config.drive.allowed_rise_c} min={1} max={100} step={5} ariaLabel="Allowed trace temperature rise (°C)" class={field} onCommit={(v) => update({ allowed_rise_c: v })} /></SettingRow>
        <SettingRow label="Via plating (µm)" help="Barrel plating thickness. 25 µm is the IPC class 2 minimum average."><NumberField value={Math.round(config.drive.via_plating_m * 1e6)} min={5} max={100} step={5} ariaLabel="Via plating thickness (µm)" class={field} onCommit={(v) => update({ via_plating_m: v * 1e-6 })} /></SettingRow>
      </div>
    </fieldset>
  </div>
</section>
