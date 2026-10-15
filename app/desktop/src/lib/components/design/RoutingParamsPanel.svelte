<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { RoutingParamDef } from "../../types";
  import NumberField from "../ui/NumberField.svelte";
  import HelpTag from "../ui/HelpTag.svelte";
  import WindingConnectionHelp from "./WindingConnectionHelp.svelte";

  let { config }: { config: ConfigStore } = $props();

  /** Current value for a def, falling back to its declared default. */
  function valueFor(def: RoutingParamDef): number {
    const value = config.routing_params[def.key];
    return typeof value === "number" && Number.isFinite(value) ? value : def.default;
  }

  /** The braid's winding connection gets a wiring diagram in its tooltip. */
  function hasDiagram(def: RoutingParamDef): boolean {
    return def.key === "connection" && config.routing_pattern === "infinity-braid";
  }

  function onParamInput(def: RoutingParamDef, value: number): void {
    if (!Number.isFinite(value)) return;
    config.setRoutingParam(def.key, value);
  }
</script>

<div class="space-y-2">
  {#if config.routing_param_defs.length === 0}
    <p class="text-xs italic text-slate-500">No user-editable parameters for this pattern.</p>
  {:else}
    <div class="grid gap-x-3 gap-y-1.5 sm:grid-cols-2" role="list">
      {#each config.routing_param_defs as def (def.key)}
        <label class="min-w-0">
          <span class="flex items-center justify-between gap-2">
            <span class="min-w-0 truncate text-xs text-slate-300">
              {def.label}
              <span class="font-mono text-[10px] text-slate-500">({def.key})</span>
              {#if hasDiagram(def)}
                <HelpTag label="About winding connection">
                  <WindingConnectionHelp />
                </HelpTag>
              {:else if def.description}
                <HelpTag tip={def.description} />
              {/if}
            </span>
            {#if def.options?.length}
              <select
                id={`routing-param-${def.key}`}
                aria-label={def.label}
                class="w-32 shrink-0 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-emerald-200"
                value={valueFor(def)}
                onchange={(event) => onParamInput(def, Number(event.currentTarget.value))}
              >
                {#each def.options as option (option.value)}
                  <option value={option.value}>{option.label}</option>
                {/each}
              </select>
            {:else}
              <NumberField
                id={`routing-param-${def.key}`}
                value={valueFor(def)}
                step={def.multiple_of ?? def.step ?? (def.param_type === "int" ? 1 : 0.1)}
                integer={def.param_type === "int"}
                min={def.min}
                max={def.max}
                multipleOf={def.multiple_of ?? undefined}
                ariaLabel={def.label}
                class="w-24 shrink-0 bg-slate-900 px-2 py-1 text-xs font-mono text-emerald-200"
                onCommit={(value) => onParamInput(def, value)}
              />
            {/if}
          </span>
          {#if !def.options?.length && (def.min !== undefined || def.max !== undefined || def.multiple_of)}
            <span class="mt-0.5 block text-[10px] text-slate-500">
              range {def.min ?? "-"} to {def.max ?? "-"}{def.multiple_of
                ? ` · multiples of ${def.multiple_of}`
                : ""}
            </span>
          {/if}
        </label>
      {/each}
    </div>
  {/if}
</div>