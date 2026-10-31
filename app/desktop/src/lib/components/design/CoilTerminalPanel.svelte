<script lang="ts">
  import type { CoilTerminalTool } from "../../utils/coilTerminalTool.svelte";
  import type { CadGeometry } from "../../types";
  import { terminalDescription, defaultCadTerminals } from "../../cadTerminals";
  import { cadCoilNames } from "../../cadPreview";
  import type { WindingConnection } from "../../types/routing";
  import type { RoutingParamDef } from "../../types";
  import { windingConnectionLabel } from "../../routingSources";
  import HelpTag from "../ui/HelpTag.svelte";
  import WindingConnectionHelp from "./WindingConnectionHelp.svelte";
  import NumberField from "../ui/NumberField.svelte";
  let { tool, geometry, onStart, disabled = false, declaredConnection = null, connectionLocked = false, connectionParam, connectionValue, onConnectionParamChange }: {
    tool: CoilTerminalTool; geometry: CadGeometry; onStart: (coil?: string) => void; disabled?: boolean;
    declaredConnection?: WindingConnection | null;
    connectionLocked?: boolean;
    connectionParam?: RoutingParamDef;
    connectionValue?: number;
    onConnectionParamChange?: (value: number) => void;
  } = $props();
  const group = $props.id();
  let phases = $derived.by(() => {
    const groups = new Map<string, string[]>();
    for (const coil of cadCoilNames(geometry)) {
      const phase = Object.hasOwn(geometry.coil_phases ?? {}, coil) ? geometry.coil_phases![coil] : coil;
      groups.set(phase, [...(groups.get(phase) ?? []), coil]);
    }
    return [...groups].sort(([a], [b]) => a.localeCompare(b));
  });
  function select(coil: string, role: "input" | "output") {
    if (tool.active && tool.coil !== coil) {
      tool.error = "Apply or cancel the current coil before selecting another.";
      return;
    }
    if (!tool.active) onStart(coil);
    tool.change(role);
  }
  function autoSelect() {
    if (!tool.active) onStart();
    tool.autoSelect();
  }
</script>

<section aria-label="Set coil terminals" class="space-y-3 text-xs text-slate-300">
  <div class="flex flex-wrap items-center justify-between gap-2">
    <span class="font-semibold text-slate-400">Winding connection<HelpTag label="About winding connection"><WindingConnectionHelp /></HelpTag></span>
    {#if connectionLocked || declaredConnection}
      <span class="text-emerald-300" aria-label="Generator winding connection">{declaredConnection ? windingConnectionLabel(declaredConnection) : "Unknown end type"}</span>
    {:else if connectionParam?.options?.length && onConnectionParamChange}
      <select id={`${group}-connection`} aria-label="Winding connection" disabled={disabled} value={connectionValue ?? connectionParam.default} onchange={(event) => onConnectionParamChange?.(Number(event.currentTarget.value))} class="min-w-0 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-emerald-200">
        {#each connectionParam.options as option (option.value)}<option value={option.value}>{option.label}</option>{/each}
      </select>
    {:else if connectionParam && onConnectionParamChange}
      <NumberField id={`${group}-connection`} ariaLabel="Winding connection" disabled={disabled}
        value={connectionValue ?? connectionParam.default} min={connectionParam.min} max={connectionParam.max}
        step={connectionParam.multiple_of ?? connectionParam.step ?? 1} integer={connectionParam.param_type === "int"}
        multipleOf={connectionParam.multiple_of ?? undefined} onCommit={(value) => onConnectionParamChange?.(value)}
        class="w-24 shrink-0 bg-slate-900 px-2 py-1 text-xs font-mono text-emerald-200" />
    {:else}
      <select id={`${group}-connection`} aria-label="Winding connection" disabled={disabled} value={tool.connection} onchange={(event) => tool.setConnection(event.currentTarget.value as "star" | "delta")} class="min-w-0 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-emerald-200">
        <option value="star">Star (Wye)</option><option value="delta">Delta</option>
      </select>
    {/if}
  </div>
  {#if declaredConnection}<p class="text-[11px] text-slate-500">Set by the routing source.</p>
  {:else if connectionLocked}<p class="text-[11px] text-amber-300">Choose a routing source with a declared connection.</p>{/if}
  <button type="button" disabled={disabled || !tool.coils.length || declaredConnection === "closed" || (connectionLocked && !declaredConnection)} onclick={autoSelect} class="rounded border border-emerald-500/50 px-2 py-1.5 text-emerald-300 disabled:opacity-40">Auto-select ends</button>
  {#if tool.notice}<p role="status" class="text-[11px] text-emerald-300">{tool.notice}</p>{/if}
  {#if tool.error}<p role="alert" class="text-rose-300">{tool.error}</p>{/if}
  <p class="text-[11px] text-slate-400">Select the driver end. The opposite end is identified automatically. {tool.connection === "star" ? "Neutral ends meet at the shared neutral junction." : "Each delta end connects to the next coil's driver end."} This marks coil ends only; connecting traces are not added.</p>
  {#if !phases.length}<p>No trace endpoints available.</p>{/if}
  {#each phases as [phase, coils] (phase)}
    <details open class="border-b border-slate-700 pb-2">
      <summary class="cursor-pointer py-2 font-semibold">Phase {phase}</summary>
      {#each coils as coil (coil)}
        {@const inferred = defaultCadTerminals(geometry, coil)}
        {#if coil !== phase || coils.length > 1}<p class="ml-3 py-1 text-slate-400">Coil {coil}</p>{/if}
        <div class="ml-3 border-l border-slate-700 pl-2">
          {#each ["input", "output"] as role (role)}
            {@const key = role as "input" | "output"}
            {@const point = tool.active && tool.coil === coil ? tool[key] : geometry.coil_terminals?.[coil]?.[key]}
            {@const picking = tool.active && tool.coil === coil && tool.step === key}
            <div class="border-b border-slate-800 py-2">
              <div class="flex items-center gap-2">
                <span class={point ? "text-emerald-300" : "text-slate-500"} aria-label={point ? "Selected" : "Not selected"}>{point ? "●" : "○"}</span>
                <span class="flex-1 font-semibold">{key === "input" ? "Driver end" : tool.connection === "star" ? "Neutral end" : "Delta end"}</span>
                {#if key === "input" || !inferred}
                  <button type="button" disabled={disabled || !tool.coils.includes(coil)} aria-label={`Select ${key === "input" ? "driver end" : tool.connection === "star" ? "neutral end" : "delta end"} for coil ${coil}`} aria-pressed={picking} onclick={() => select(coil, key)} class="rounded border border-slate-600 px-2 py-1 text-xs aria-pressed:border-emerald-400 aria-pressed:text-emerald-300 disabled:opacity-40">{picking ? "Picking…" : "Select"}</button>
                {:else}<span class="text-[10px] text-slate-400">Automatic</span>{/if}
              </div>
              <p class="mt-1 break-words text-[10px] text-slate-400">{point ? terminalDescription(point) : "Not selected"}</p>
            </div>
          {/each}
        </div>
      {/each}
    </details>
  {/each}
  {#if tool.active}
    <p role="status" class="text-emerald-300">{tool.step === "input" ? `Select the driver end for ${tool.coil}.` : tool.step === "output" ? `Couldn't identify the opposite end. Select the ${tool.connection === "star" ? "neutral" : "delta"} end for ${tool.coil}.` : `Review ${tool.coil}, then apply.`}</p>
    <p class="text-[11px] text-slate-400">Use the layer slider to show the endpoints on each layer.</p>
    <div class="flex flex-wrap gap-2">
      <button type="button" onclick={tool.done} disabled={disabled || !tool.canApply} class="rounded border border-emerald-500/50 px-2 py-1.5 text-emerald-300 disabled:opacity-40">Apply terminals</button>
      <button type="button" onclick={tool.flip} disabled={disabled || !tool.input || !tool.output} class="rounded border border-slate-700 px-2 py-1.5 disabled:opacity-40">Flip</button>
      <button type="button" onclick={tool.cancel} class="px-2 py-1.5 text-slate-400">Cancel</button>
      {#if (tool.step === "input" || tool.step === "output") && tool.input && tool.output}<button type="button" onclick={tool.finishPicking} class="px-2 py-1.5 text-slate-400">Keep current points</button>{/if}
    </div>
    <p class="text-[10px] text-slate-500">Apply before selecting another coil. Unapplied changes are discarded when this panel closes.</p>
  {/if}
</section>
