<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { DriveSettings, DriverSpec } from "../../types";
  import NumberField from "../ui/NumberField.svelte";
  import Separator from "../ui/Separator.svelte";
  import SettingRow from "./SettingRow.svelte";
  import AddDriverModal from "./AddDriverModal.svelte";
  import { driverLibrary } from "../../stores/driverLibrary.svelte";

  let { config }: { config: ConfigStore } = $props();

  const COPPER_WEIGHTS = [0.5, 1, 2, 3];

  let addingDriver = $state(false);
  // The driver library is the single source of selectable drivers. The
  // project's own driver stays first even when the library no longer holds it
  // (an older project, or a library entry that was removed).
  let drivers = $derived([
    config.drive.driver,
    ...driverLibrary.drivers.filter((driver) => driver.name !== config.drive.driver.name),
  ]);

  function update(patch: Partial<DriveSettings>): void {
    config.drive = { ...config.drive, ...patch };
  }

  function choosePreset(name: string): void {
    const preset = drivers.find((p) => p.name === name);
    const current = config.drive.driver;
    if (!driverLibrary.drivers.some((driver) => driver.name === current.name)) {
      driverLibrary.add(current);
    }
    if (preset) update({ driver: { ...preset } });
  }

  function addDriver(driver: DriverSpec): void {
    driverLibrary.add(driver);
    update({ driver });
    addingDriver = false;
  }

  const field = "w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200";
  const selectClass =
    "w-24 shrink-0 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400";
</script>


<section aria-labelledby="driver-settings-heading" class="overflow-hidden rounded-md border border-slate-700 bg-slate-800/30">
  <div class="flex items-center justify-between gap-3 px-3 py-2">
    <h3 id="driver-settings-heading" class="text-xs font-semibold uppercase tracking-wider text-slate-200">Driver</h3>
    <button type="button" onclick={() => (addingDriver = true)} class="rounded border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-700">Add driver…</button>
  </div>
  <div class="px-3 pb-3">
    <label for="evaluation-driver" class="mb-1 block text-[11px] text-slate-400">Evaluate against</label>
    <select
      id="evaluation-driver"
      aria-label="Driver to evaluate"
      value={config.drive.driver.name}
      onchange={(e) => choosePreset(e.currentTarget.value)}
      class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400"
    >
      {#each drivers as preset (preset.name)}
        <option value={preset.name}>{preset.name}</option>
      {/each}
    </select>
    <p class="mt-2 text-[11px] text-slate-400">{config.drive.driver.min_supply_v}–{config.drive.driver.max_supply_v} V · {config.drive.driver.continuous_rms_a} A RMS · {config.drive.driver.peak_current_a} A peak</p>
    <p class="mt-1 text-[11px] text-slate-400">{config.drive.driver.supports_delta ? "Delta handling declared" : "Requires Star (wye) for evaluation"}</p>
    {#if !driverLibrary.storageAvailable}<p role="status" class="mt-2 text-xs text-amber-200">Driver selected. Library storage is unavailable, so save this project to keep its parameters.</p>{/if}
  </div>

  <Separator />

  <div class="space-y-3 px-3 pb-3 pt-2.5">
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

{#if addingDriver}
  <AddDriverModal existingNames={drivers.map((driver) => driver.name)} onAdd={addDriver} onClose={() => (addingDriver = false)} />
{/if}
