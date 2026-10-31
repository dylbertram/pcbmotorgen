<script lang="ts">
  import type { ConfigStore } from "../../../stores/config.svelte";
  import type { DriveSettings } from "../../../types";
  import SettingRow from "../../simulate/SettingRow.svelte";

  let { config }: { config: ConfigStore } = $props();
  const weights = [0.5, 1, 2, 3];
  const headingId = $props.id();
  function update(patch: Partial<DriveSettings>): void {
    config.drive = { ...config.drive, ...patch };
  }
</script>

<section aria-labelledby={headingId} class="space-y-2 border-t border-slate-700 pt-3">
  <h3 id={headingId} class="text-xs font-semibold text-slate-300">Copper</h3>
  {#if config.pcb_stackup_mm}<p class="text-[11px] text-slate-400">Copper thickness is defined per layer below. These weights apply only when custom stackup is off.</p>{/if}
  <SettingRow label="Outer layers" help="Finished copper weight. 1 oz ≈ 35 µm, 2 oz ≈ 70 µm.">
    <select aria-label="Outer layer copper weight" disabled={!!config.pcb_stackup_mm} value={String(config.drive.outer_copper_oz)} onchange={(e) => update({ outer_copper_oz: Number(e.currentTarget.value) })} class="w-24 shrink-0 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">
      {#each weights as oz (oz)}<option value={String(oz)}>{oz} oz</option>{/each}
    </select>
  </SettingRow>
  <SettingRow label="Inner layers">
    <select aria-label="Inner layer copper weight" disabled={!!config.pcb_stackup_mm} value={String(config.drive.inner_copper_oz)} onchange={(e) => update({ inner_copper_oz: Number(e.currentTarget.value) })} class="w-24 shrink-0 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">
      {#each weights as oz (oz)}<option value={String(oz)}>{oz} oz</option>{/each}
    </select>
  </SettingRow>
</section>
