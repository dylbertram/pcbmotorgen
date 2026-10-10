<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import { Select } from "bits-ui";
  import { formatLayerRange } from "../../layerConstraints";
  import Separator from "../ui/Separator.svelte";
  import RoutingParamsPanel from "./RoutingParamsPanel.svelte";
  import GeneratorUploadPanel from "../plugins/GeneratorUploadPanel.svelte";

  let { config, cadGeometryActive = false, onImportCad, onUseGenerated }: {
    config: ConfigStore;
    cadGeometryActive?: boolean;
    onImportCad: () => void;
    onUseGenerated: () => void;
  } = $props();

  /** Sentinel value for the "load a new generator" dropdown entry. */
  const LOAD_VALUE = "__load_generator__";
  const FILE_VALUE = "__load_design_file__";
  const IMPORTED_VALUE = "__imported_design__";

  let modalOpen = $state(false);

  /** Pattern-declared layer range, shown beside the layer selector. */
  const layerRangeLabel = $derived(formatLayerRange(config.patternLayerRange));

  // Pull the selected pattern's declared user-editable params whenever the
  // pattern changes (also on initial mount). The store reseeds defaults for
  // keys the user hasn't set yet and re-constrains the layer count against
  // the pattern's declared range.
  $effect(() => {
    if (cadGeometryActive) return;
    const id = config.routing_pattern;
    void config.loadRoutingParams(id);
  });

  // File import and generator upload are actions, not routing pattern IDs.
  // Function binding keeps the active source selected when either dialog closes.
  function patternBindingGet(): string {
    if (cadGeometryActive) return IMPORTED_VALUE;
    return config.routing_patterns.length === 0 ? "" : config.routing_pattern;
  }

  function patternBindingSet(v: string): void {
    if (v === FILE_VALUE) {
      onImportCad();
      return;
    }
    if (v === IMPORTED_VALUE) return;
    if (v === LOAD_VALUE) {
      modalOpen = true;
      return;
    }
    config.routing_pattern = v;
    onUseGenerated();
  }

  // `items` powers label lookup in Select.Value while the portal content is
  // unmounted (so the trigger shows display names, never raw ids) and
  // native-style typeahead on the closed trigger.
  const patternItems = $derived(
    [
          ...(cadGeometryActive ? [{ value: IMPORTED_VALUE, label: "Imported DXF design" }] : []),
          ...config.routing_patterns.map((p) => ({
            value: p.id,
            label: p.display_name,
          })),
          { value: LOAD_VALUE, label: "+ Load new generator…" },
          { value: FILE_VALUE, label: "Load design from file…" },
        ],
  );

  const layerValue = $derived(String(config.num_layers));
  const layerItems = $derived(
    config.layerOptions.map((n) => ({ value: String(n), label: String(n) })),
  );

  function onLayerValueChange(v: string): void {
    const value = Number(v);
    // The selector only offers valid counts (even, >= 2, within the board
    // stackup and the pattern's range); guard anyway so nothing but a whole
    // number reaches the store.
    if (Number.isInteger(value) && value >= 2) {
      config.num_layers = value;
    }
  }
</script>

<div class="space-y-2.5">
  <!-- The source selector and heading share a row in the Topology & Board panel. -->
  <div class="flex flex-wrap items-center gap-2">
    <h3
      id="routing-source-heading"
      class="text-[11px] font-semibold uppercase tracking-wider text-slate-300"
    >
      Routing source
    </h3>

    <Select.Root
      type="single"
      bind:value={patternBindingGet, patternBindingSet}
      items={patternItems}
    >
      <Select.Trigger
        id="routing-pattern"
        aria-label="Routing source"
        class="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs text-slate-100 focus:border-emerald-500 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 flex items-center justify-between gap-1 text-left"
      >
        <Select.Value placeholder="Loading patterns…" />
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
      <Select.Portal>
        <Select.Content
          class="z-50 max-h-72 min-w-[var(--bits-select-anchor-width)] overflow-y-auto rounded-md border border-slate-700 bg-slate-800 py-1 shadow-lg shadow-black/40 focus:outline-none"
        >
          {#if cadGeometryActive}
            <Select.Item value={IMPORTED_VALUE} label="Imported DXF design" class="px-2.5 py-1.5 text-xs text-sky-200 outline-none data-[highlighted]:bg-slate-700/60">Imported DXF design</Select.Item>
          {/if}
          {#each config.routing_patterns as pattern (pattern.id)}
            <Select.Item
              value={pattern.id}
              label={pattern.display_name}
              class="flex cursor-pointer items-center justify-between gap-2 px-2.5 py-1.5 text-xs text-slate-100 outline-none data-[selected]:bg-slate-700 data-[highlighted]:bg-slate-700/60 data-[highlighted]:text-emerald-200 data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50"
            >
              {pattern.display_name}
            </Select.Item>
          {/each}
          {#if config.routing_patterns.length > 0}
            <!-- Design-system divider (kata tn66): decorative, purely
                 visual inside the listbox — neither focusable nor
                 selectable. -->
            <Separator class="my-1" />
          {/if}
          <Select.Item
            value={LOAD_VALUE}
            label="+ Load new generator…"
            class="flex cursor-pointer items-center justify-between gap-2 px-2.5 py-1.5 text-xs text-emerald-300 outline-none data-[selected]:bg-slate-700 data-[highlighted]:bg-slate-700/60 data-[highlighted]:text-emerald-200 data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50"
          >
            + Load new generator…
          </Select.Item>
          <Separator class="my-1" />
          <Select.Item value={FILE_VALUE} label="Load design from file…" class="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-xs text-emerald-300 outline-none data-[highlighted]:bg-slate-700/60 data-[highlighted]:text-emerald-200">
            Load design from file…
          </Select.Item>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  </div>

  <!-- Copper-layer count: options are the even ladder (>= 2, <= max_layers)
       intersected with the active pattern's declared range; the caption shows
       that range and updates on pattern switch. The selector can only OFFER
       valid values — the Rust config validation and the routing crate's
       generate-time layer check remain the authorities. -->
  {#if !cadGeometryActive}
  <div class="flex flex-wrap items-center gap-2">
    <label
      for="num-layers"
      class="text-[11px] font-semibold uppercase tracking-wider text-slate-300"
    >
      Copper layers
    </label>
    <Select.Root
      type="single"
      value={layerValue}
      onValueChange={onLayerValueChange}
      disabled={config.layerOptions.length <= 1}
      items={layerItems}
    >
      <Select.Trigger
        id="num-layers"
        aria-label="Copper layer count"
        class="rounded-md border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs text-slate-100 focus:border-emerald-500 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 flex items-center gap-1 text-left"
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
      <Select.Portal>
        <Select.Content
          class="z-50 max-h-72 min-w-[var(--bits-select-anchor-width)] overflow-y-auto rounded-md border border-slate-700 bg-slate-800 py-1 shadow-lg shadow-black/40 focus:outline-none"
        >
          {#each config.layerOptions as n (n)}
            <Select.Item
              value={String(n)}
              label={String(n)}
              class="flex cursor-pointer items-center justify-between gap-2 px-2.5 py-1.5 text-xs text-slate-100 outline-none data-[selected]:bg-slate-700 data-[highlighted]:bg-slate-700/60 data-[highlighted]:text-emerald-200 data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50"
            >
              {n}
            </Select.Item>
          {/each}
        </Select.Content>
      </Select.Portal>
    </Select.Root>
    <span class="min-w-0 flex-1 text-[10px] text-slate-500" role="note">
      {layerRangeLabel}
    </span>
  </div>

  <RoutingParamsPanel {config} />
  {/if}
</div>

{#if modalOpen}
  <GeneratorUploadPanel {config} onClose={() => (modalOpen = false)} />
{/if}
