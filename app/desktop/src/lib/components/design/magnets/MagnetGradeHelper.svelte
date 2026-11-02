<script lang="ts">
  import type { ConfigStore } from "../../../stores/config.svelte";
  import { Select } from "bits-ui";
  import { CUSTOM_GRADE } from "../../../types";
  import NumberField from "../../ui/NumberField.svelte";

  let { config }: { config: ConfigStore } = $props();

  let selected = $derived(config.magnet_grade);

  // Grade info comes from the runtime-loaded backend table when available;
  // the static TS table in types/magnets.ts is the offline fallback.
  let gradeInfo = $derived.by(() => {
    if (selected === CUSTOM_GRADE) return null;
    return config.getMagnetGrade(selected);
  });

  let tempSuffixes = $derived(
    gradeInfo ? Object.entries(gradeInfo.max_temp_c) : [],
  );

  const gradeItems = $derived([
    ...config.magnetGradeNames.map((name) => ({ value: name, label: name })),
    { value: CUSTOM_GRADE, label: CUSTOM_GRADE },
  ]);

  function onGradeValueChange(v: string): void {
    config.magnet_grade = v;
    config.syncGrade();
  }
</script>

<div class="space-y-1.5">
  <Select.Root
    type="single"
    value={selected}
    onValueChange={onGradeValueChange}
    items={gradeItems}
  >
    <div class="flex items-center justify-between gap-2">
      <span class="text-xs text-slate-300">Magnet grade</span>
      <Select.Trigger
        id="magnet-grade"
        aria-label="Magnet grade"
        class="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs text-slate-100 focus:border-emerald-500 focus:outline-none flex items-center justify-between gap-1 text-left"
      >
        <Select.Value />
        <svg
          viewBox="0 0 12 12"
          class="h-3 w-3 shrink-0 text-slate-500"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          aria-hidden="true"
        >
          <path d="M2.5 4.5 6 8l3.5-3.5" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </Select.Trigger>
    </div>
    <Select.Portal>
      <Select.Content
        class="z-50 max-h-72 min-w-[var(--bits-select-anchor-width)] overflow-y-auto rounded-md border border-slate-700 bg-slate-800 py-1 shadow-lg shadow-black/40 focus:outline-none"
      >
        {#each config.magnetGradeNames as name (name)}
          <Select.Item
            value={name}
            label={name}
            class="flex cursor-pointer items-center justify-between gap-2 px-2.5 py-1.5 text-xs text-slate-100 outline-none data-[selected]:bg-slate-700 data-[highlighted]:bg-slate-700/60 data-[highlighted]:text-emerald-200 data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50"
          >
            {name}
          </Select.Item>
        {/each}
        <Select.Item
          value={CUSTOM_GRADE}
          label={CUSTOM_GRADE}
          class="flex cursor-pointer items-center justify-between gap-2 px-2.5 py-1.5 text-xs text-slate-100 outline-none data-[selected]:bg-slate-700 data-[highlighted]:bg-slate-700/60 data-[highlighted]:text-emerald-200 data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50"
        >
          {CUSTOM_GRADE}
        </Select.Item>
      </Select.Content>
    </Select.Portal>
  </Select.Root>

  {#if gradeInfo}
    <div class="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-slate-500">
      <span>Reference Br {gradeInfo.br_min_t.toFixed(2)}–{gradeInfo.br_max_t.toFixed(2)} T</span>
      <span>typ {gradeInfo.br_typ_t.toFixed(2)} T</span>
      {#each tempSuffixes as [suffix, temp] (suffix)}
        <span>{suffix} {temp}°C</span>
      {/each}
      <span class="text-emerald-400/80">auto Br {config.magnet_remanence_t.toFixed(2)} T</span>
    </div>
  {:else}
    <label
      class="flex items-center justify-between gap-2 text-xs text-slate-400"
      for="custom-magnet-remanence"
    >
      <span>Custom remanence Br (T)</span>
      <NumberField
        id="custom-magnet-remanence"
        step={0.01}
        min={0.0001}
        max={2.5}
        value={config.magnet_remanence_t}
        ariaLabel="Custom magnet remanence (T)"
        class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
        onCommit={(value) => (config.magnet_remanence_t = value)}
      />
    </label>
  {/if}
</div>
