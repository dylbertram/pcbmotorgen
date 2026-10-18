<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { DriverSpec } from "../../types";
  import { driverLibrary } from "../../stores/driverLibrary.svelte";
  import AddDriverModal from "./AddDriverModal.svelte";

  let { config }: { config: ConfigStore } = $props();
  const id = $props.id();
  let addingDriver = $state(false);
  let drivers = $derived([
    config.drive.driver,
    ...driverLibrary.drivers.filter((driver) => driver.name !== config.drive.driver.name),
  ]);

  function choosePreset(name: string): void {
    const preset = drivers.find((driver) => driver.name === name);
    const current = config.drive.driver;
    if (!driverLibrary.drivers.some((driver) => driver.name === current.name)) {
      driverLibrary.add(current);
    }
    if (preset) config.drive = { ...config.drive, driver: { ...preset } };
  }

  function addDriver(driver: DriverSpec): void {
    driverLibrary.add(driver);
    config.drive = { ...config.drive, driver };
    addingDriver = false;
  }
</script>

<div class="space-y-2">
  <div class="flex flex-wrap items-center justify-between gap-2">
    <label for={id} class="text-[11px] text-slate-400">Evaluate against</label>
    <button type="button" onclick={() => (addingDriver = true)} class="rounded border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-700">Add driver…</button>
  </div>
  <select id={id} aria-label="Driver to evaluate" value={config.drive.driver.name}
    onchange={(event) => choosePreset(event.currentTarget.value)}
    class="w-full min-w-0 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400">
    {#each drivers as driver (driver.name)}<option value={driver.name}>{driver.name}</option>{/each}
  </select>
  <p class="text-[11px] text-slate-400">{config.drive.driver.min_supply_v}–{config.drive.driver.max_supply_v} V · {config.drive.driver.continuous_rms_a} A RMS · {config.drive.driver.peak_current_a} A peak</p>
  <p class="text-[11px] text-slate-400">{config.drive.driver.supports_delta ? "Delta handling declared" : "Requires Star (wye) for evaluation"}</p>
  {#if !driverLibrary.storageAvailable}<p role="status" class="text-xs text-amber-200">Driver selected. Library storage is unavailable, so save this project to keep its parameters.</p>{/if}
</div>

{#if addingDriver}
  <AddDriverModal existingNames={drivers.map((driver) => driver.name)} onAdd={addDriver} onClose={() => (addingDriver = false)} />
{/if}
