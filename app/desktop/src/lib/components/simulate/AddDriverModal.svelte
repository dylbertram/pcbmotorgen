<script lang="ts">
  import { Dialog } from "bits-ui";
  import type { DriverSpec } from "../../types";
  import { driverValidationError } from "../../driverLibrary";

  let { existingNames, onAdd, onClose }: {
    existingNames: string[];
    onAdd: (driver: DriverSpec) => void;
    onClose: () => void;
  } = $props();

  let open = $state(true);
  let error = $state<string | null>(null);
  const inputClass = "mt-1 w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400";

  function submit(event: SubmitEvent): void {
    event.preventDefault();
    const data = new FormData(event.currentTarget as HTMLFormElement);
    const driver: DriverSpec = {
      name: String(data.get("name") ?? "").trim(),
      supports_delta: data.get("supports_delta") === "on",
      min_supply_v: Number(data.get("min_supply_v")),
      max_supply_v: Number(data.get("max_supply_v")),
      peak_current_a: Number(data.get("peak_current_a")),
      continuous_rms_a: Number(data.get("continuous_rms_a")),
      rds_on_ohm: Number(data.get("rds_on_mohm")) / 1e3,
      max_pwm_hz: Number(data.get("max_pwm_khz")) * 1e3,
    };
    error = driverValidationError(driver);
    if (!error && existingNames.some((name) => name.toLowerCase() === driver.name.toLowerCase())) {
      error = "A driver with this name already exists. Choose another name.";
    }
    if (error) return;
    onAdd(driver);
  }
</script>

<Dialog.Root bind:open onOpenChange={(value) => { if (!value) onClose(); }}>
  <Dialog.Portal>
    <Dialog.Overlay class="fixed inset-0 z-50 bg-black/70" />
    <Dialog.Content class="fixed left-1/2 top-1/2 z-50 max-h-[85vh] w-[calc(100%_-_2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-slate-700 bg-slate-800 p-5 shadow-xl">
      <Dialog.Title class="text-sm font-semibold text-slate-100">Add driver</Dialog.Title>
      <Dialog.Description class="mt-1 text-xs text-slate-400">Enter the datasheet limits. The new driver will be selected for evaluation.</Dialog.Description>
      <form onsubmit={submit} class="mt-4 space-y-4">
        <label class="block text-xs text-slate-300">Driver name
          <input name="name" required maxlength={100} class={inputClass} />
        </label>
        <div class="grid grid-cols-2 gap-3">
          <label class="text-xs text-slate-300">Min supply (V)<input name="min_supply_v" type="number" required min="0" step="any" class={inputClass} /></label>
          <label class="text-xs text-slate-300">Max supply (V)<input name="max_supply_v" type="number" required min="0.001" step="any" class={inputClass} /></label>
          <label class="text-xs text-slate-300">Peak / OCP (A)<input name="peak_current_a" type="number" required min="0.001" step="any" class={inputClass} /></label>
          <label class="text-xs text-slate-300">Continuous (A RMS)<input name="continuous_rms_a" type="number" required min="0.001" step="any" class={inputClass} /></label>
          <label class="text-xs text-slate-300">R_DS(on) HS+LS (mΩ)<input name="rds_on_mohm" type="number" required min="0" step="any" class={inputClass} /></label>
          <label class="text-xs text-slate-300">Max PWM (kHz)<input name="max_pwm_khz" type="number" required min="0.001" step="any" class={inputClass} /></label>
        </div>
        <label class="flex items-start gap-2 text-xs text-slate-300">
          <input name="supports_delta" type="checkbox" class="mt-0.5 accent-emerald-500" />
          <span>Built-in delta handling
            <span class="mt-1 block text-[11px] text-slate-400">Enable only when the driver/controller documentation confirms support. Delta electrical analysis is not yet available in this app.</span>
          </span>
        </label>
        {#if error}<p role="alert" class="text-xs text-rose-300">{error}</p>{/if}
        <div class="flex justify-end gap-2">
          <Dialog.Close class="rounded border border-slate-600 px-3 py-2 text-xs text-slate-200">Cancel</Dialog.Close>
          <button type="submit" class="rounded bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-500">Add driver</button>
        </div>
      </form>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
