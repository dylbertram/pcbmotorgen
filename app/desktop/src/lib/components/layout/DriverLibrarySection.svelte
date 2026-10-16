<script lang="ts">
  import type { DriverSpec } from "../../types";
  import { DRIVER_PRESETS } from "../../types";
  import { driverValidationError } from "../../driverLibrary";
  import { driverLibrary } from "../../stores/driverLibrary.svelte";
  import AddDriverModal from "../simulate/AddDriverModal.svelte";

  let { disabled = false }: { disabled?: boolean } = $props();

  /** Names of the drivers shipped with the app (still ordinary library rows). */
  const bundledNames = new Set(DRIVER_PRESETS.map((driver) => driver.name));

  /** Editable form values: datasheet-friendly units (mΩ, kHz) like the Add dialog. */
  interface DriverDraft {
    name: string;
    supports_delta: boolean;
    min_supply_v: number;
    max_supply_v: number;
    peak_current_a: number;
    continuous_rms_a: number;
    rds_on_mohm: number;
    max_pwm_khz: number;
  }

  let editingIndex = $state<number | null>(null);
  let draft = $state<DriverDraft | null>(null);
  let error = $state<string | null>(null);
  let adding = $state(false);

  const field = "w-24 shrink-0 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-right text-xs tabular-nums focus:border-emerald-500 focus:outline-none";

  function toDraft(driver: DriverSpec): DriverDraft {
    return {
      name: driver.name,
      supports_delta: driver.supports_delta === true,
      min_supply_v: driver.min_supply_v,
      max_supply_v: driver.max_supply_v,
      peak_current_a: driver.peak_current_a,
      continuous_rms_a: driver.continuous_rms_a,
      rds_on_mohm: Math.round(driver.rds_on_ohm * 1e4) / 10,
      max_pwm_khz: driver.max_pwm_hz / 1e3,
    };
  }

  function edit(index: number): void {
    editingIndex = index;
    draft = toDraft(driverLibrary.drivers[index]);
    error = null;
  }

  function cancel(): void {
    editingIndex = null;
    draft = null;
    error = null;
  }

  function save(): void {
    if (editingIndex === null || !draft) return;
    const driver: DriverSpec = {
      name: draft.name.trim(),
      supports_delta: draft.supports_delta,
      min_supply_v: Number(draft.min_supply_v),
      max_supply_v: Number(draft.max_supply_v),
      peak_current_a: Number(draft.peak_current_a),
      continuous_rms_a: Number(draft.continuous_rms_a),
      rds_on_ohm: Number(draft.rds_on_mohm) / 1e3,
      max_pwm_hz: Number(draft.max_pwm_khz) * 1e3,
    };
    const invalid = driverValidationError(driver);
    if (invalid) {
      error = invalid;
      return;
    }
    const name = driver.name.toLowerCase();
    if (driverLibrary.drivers.some((saved, i) => i !== editingIndex && saved.name.trim().toLowerCase() === name)) {
      error = "A driver with this name already exists. Choose another name.";
      return;
    }
    driverLibrary.update(editingIndex, driver);
    cancel();
  }

  function remove(index: number): void {
    if (editingIndex === index) cancel();
    driverLibrary.remove(index);
  }

  function add(driver: DriverSpec): void {
    driverLibrary.add(driver);
    adding = false;
  }
</script>

<fieldset disabled={disabled}>
  <legend class="text-sm font-semibold">Driver library</legend>
  <div class="mt-2 flex items-center justify-between gap-3">
    <p class="text-xs leading-relaxed text-slate-400">
      Saved drivers are shared with the Simulation tab's driver selector.
    </p>
    <button
      type="button"
      onclick={() => (adding = true)}
      class="shrink-0 rounded-md border border-slate-700 px-2.5 py-1.5 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50"
    >
      Add driver…
    </button>
  </div>
  <p class="mb-3 mt-1 text-xs leading-relaxed text-slate-400">
    Bundled drivers ship with the app but can be edited or removed like any other. Pick a driver in the Simulation tab to evaluate against it.
  </p>

  {#if driverLibrary.drivers.length === 0}
    <p class="text-xs text-slate-500">No saved drivers yet. Add one, or create projects with the Simulation tab's Add driver flow.</p>
  {/if}

  <ul class="space-y-2">
    {#each driverLibrary.drivers as driver, index (index)}
      <li class="rounded-md border border-slate-700 bg-slate-800/40 p-3">
        {#if editingIndex === index && draft}
          <div class="grid grid-cols-2 gap-x-3 gap-y-2">
            <label class="col-span-2 text-xs text-slate-300">Name
              <input bind:value={draft.name} maxlength={100} aria-label="Driver name" class="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none" />
            </label>
            <label class="text-xs text-slate-300">Min supply (V)
              <input type="number" min="0" step="any" bind:value={draft.min_supply_v} aria-label="Driver minimum supply (V)" class={field} />
            </label>
            <label class="text-xs text-slate-300">Max supply (V)
              <input type="number" min="0.001" step="any" bind:value={draft.max_supply_v} aria-label="Driver maximum supply (V)" class={field} />
            </label>
            <label class="text-xs text-slate-300">Peak / OCP (A)
              <input type="number" min="0.001" step="any" bind:value={draft.peak_current_a} aria-label="Driver peak current (A)" class={field} />
            </label>
            <label class="text-xs text-slate-300">Continuous (A RMS)
              <input type="number" min="0.001" step="any" bind:value={draft.continuous_rms_a} aria-label="Driver continuous current (A RMS)" class={field} />
            </label>
            <label class="text-xs text-slate-300">R_DS(on) HS+LS (mΩ)
              <input type="number" min="0" step="any" bind:value={draft.rds_on_mohm} aria-label="Driver on-resistance (mΩ)" class={field} />
            </label>
            <label class="text-xs text-slate-300">Max PWM (kHz)
              <input type="number" min="0.001" step="any" bind:value={draft.max_pwm_khz} aria-label="Driver maximum PWM frequency (kHz)" class={field} />
            </label>
            <label class="col-span-2 flex items-start gap-2 text-xs text-slate-300">
              <input type="checkbox" bind:checked={draft.supports_delta} class="mt-0.5 accent-emerald-500" />
              <span>Built-in delta handling
                <span class="mt-1 block text-[11px] text-slate-400">Enable only when the driver/controller documentation confirms support. Delta electrical analysis is not yet available in this app.</span>
              </span>
            </label>
          </div>
          {#if error}<p role="alert" class="mt-2 text-xs text-rose-300">{error}</p>{/if}
          <div class="mt-3 flex justify-end gap-2">
            <button type="button" aria-label="Cancel driver edit" onclick={cancel} class="rounded border border-slate-600 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800">Cancel</button>
            <button type="button" onclick={save} class="rounded bg-emerald-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500">Save driver</button>
          </div>
        {:else}
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="flex items-center gap-1.5 text-xs font-medium text-slate-100">
                <span class="truncate" title={driver.name}>{driver.name}</span>
                {#if bundledNames.has(driver.name)}<span class="shrink-0 rounded-full border border-slate-600 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-slate-400">Bundled</span>{/if}
              </p>
              <p class="mt-0.5 text-[11px] text-slate-400">
                {driver.min_supply_v}–{driver.max_supply_v} V · {driver.continuous_rms_a} A RMS · {driver.peak_current_a} A peak · {driver.supports_delta ? "delta declared" : "star only"}
              </p>
            </div>
            <div class="flex shrink-0 gap-2">
              <button type="button" aria-label={`Edit ${driver.name}`} onclick={() => edit(index)} class="rounded border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800">Edit</button>
              <button type="button" aria-label={`Remove ${driver.name}`} onclick={() => remove(index)} class="rounded border border-rose-500/50 px-2 py-1 text-xs text-rose-200 hover:bg-rose-500/10">Remove</button>
            </div>
          </div>
        {/if}
      </li>
    {/each}
  </ul>

  {#if !driverLibrary.storageAvailable}
    <p role="status" class="mt-2 text-xs text-amber-200">Library storage is unavailable, so saved drivers will not persist across restarts.</p>
  {/if}
</fieldset>

{#if adding}
  <AddDriverModal
    zIndex={150}
    existingNames={driverLibrary.drivers.map((driver) => driver.name)}
    onAdd={add}
    onClose={() => (adding = false)}
  />
{/if}
