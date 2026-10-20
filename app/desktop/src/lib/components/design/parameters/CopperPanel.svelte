<script lang="ts">
  import type { ConfigStore } from "../../../stores/config.svelte";
  import type { DriveSettings } from "../../../types";
  import NumberField from "../../ui/NumberField.svelte";
  import SettingRow from "../../simulate/SettingRow.svelte";

  let { config }: { config: ConfigStore } = $props();
  const weights = [0.5, 1, 2, 3];
  function update(patch: Partial<DriveSettings>): void {
    config.drive = { ...config.drive, ...patch };
  }
</script>

<fieldset class="space-y-2 border-t border-slate-700 pt-3">
  <legend class="pr-2 text-xs font-semibold text-slate-300">Copper</legend>
  <SettingRow label="Outer layers" help="Finished copper weight. 1 oz ≈ 35 µm, 2 oz ≈ 70 µm.">
    <select aria-label="Outer layer copper weight" value={String(config.drive.outer_copper_oz)} onchange={(e) => update({ outer_copper_oz: Number(e.currentTarget.value) })} class="w-24 shrink-0 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">
      {#each weights as oz (oz)}<option value={String(oz)}>{oz} oz</option>{/each}
    </select>
  </SettingRow>
  <SettingRow label="Inner layers">
    <select aria-label="Inner layer copper weight" value={String(config.drive.inner_copper_oz)} onchange={(e) => update({ inner_copper_oz: Number(e.currentTarget.value) })} class="w-24 shrink-0 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">
      {#each weights as oz (oz)}<option value={String(oz)}>{oz} oz</option>{/each}
    </select>
  </SettingRow>
  <SettingRow label="Via plating (µm)" help="Barrel plating thickness. 25 µm is the IPC class 2 minimum average.">
    <NumberField value={Math.round(config.drive.via_plating_m * 1e6)} min={5} max={100} step={5} ariaLabel="Via plating thickness (µm)" class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200" onCommit={(v) => update({ via_plating_m: v * 1e-6 })} />
  </SettingRow>
</fieldset>
