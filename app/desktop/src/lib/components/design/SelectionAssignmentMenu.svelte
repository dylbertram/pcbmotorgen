<script lang="ts">
  import type { Snippet } from "svelte";
  import { ContextMenu, DropdownMenu, Dialog } from "bits-ui";
  import { ChevronRight, Ellipsis } from "@lucide/svelte";
  import type { CadGeometry } from "../../types";
  import type { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";
  import { cadCoilNames } from "../../cadPreview";

  let { tool, geometry, disabled = false, variant = "context", triggerClass = "",
    destination, onMove, children, passthrough = false }: {
    tool?: CadSelectionTool;
    geometry?: CadGeometry | null;
    disabled?: boolean;
    variant?: "context" | "button";
    triggerClass?: string;
    passthrough?: boolean;
    destination?: { coil: string; layer?: number };
    onMove?: () => void;
    children?: Snippet;
  } = $props();
  const Menu = $derived(variant === "button" ? DropdownMenu : ContextMenu);
  let newCoilOpen = $state(false);
  let coilName = $state("");
  let unavailable = $derived(disabled || !geometry || !tool?.selected.length);
  const menuClass = "z-[150] min-w-44 max-h-[var(--bits-menu-content-available-height)] overflow-y-auto rounded-md border border-slate-700 bg-slate-900 p-1 text-xs text-slate-200 shadow-xl";
  const itemClass = "flex cursor-default items-center justify-between gap-4 rounded px-3 py-2 outline-none data-[highlighted]:bg-slate-800 data-[highlighted]:text-emerald-300 data-[disabled]:opacity-40";
  function change(coil: string, layer: string) {
    if (!unavailable) tool?.apply(coil, layer);
  }
  function createCoil(event: SubmitEvent) {
    event.preventDefault();
    if (unavailable || !coilName.trim()) return;
    tool?.apply(coilName, "");
    newCoilOpen = false;
  }
</script>

<Menu.Root>
  <Menu.Trigger disabled={disabled || !geometry || (!destination && !tool?.selected.length)} class={triggerClass} style={passthrough ? "pointer-events: none" : undefined} aria-label={variant === "button" ? "Selection actions" : undefined} title={variant === "button" ? "Change the selected coil or copper layer." : undefined}>
    {#if children}{@render children()}{:else}<Ellipsis size={16} aria-hidden="true" />{/if}
  </Menu.Trigger>
  <Menu.Portal>
    <Menu.Content class={menuClass} aria-label={destination ? "Move selection" : "Selection actions"}>
      {#if destination}
        <Menu.Item class={itemClass} disabled={unavailable} onSelect={onMove}>Move to</Menu.Item>
      {:else}
        <Menu.Sub>
          <Menu.SubTrigger class={itemClass} disabled={unavailable}>Change to coil…<ChevronRight size={14} aria-hidden="true" /></Menu.SubTrigger>
          <Menu.Portal>
            <Menu.SubContent class={menuClass} aria-label="Change to coil" sideOffset={4}>
              {#each geometry ? cadCoilNames(geometry) : [] as coil (coil)}
                <Menu.Item class={itemClass} disabled={unavailable} onSelect={() => change(coil, "")}>{coil}</Menu.Item>
              {/each}
              <Menu.Separator class="my-1 h-px bg-slate-700" />
              <Menu.Item class={itemClass} disabled={unavailable} onSelect={() => { coilName = ""; newCoilOpen = true; }}>New coil…</Menu.Item>
            </Menu.SubContent>
          </Menu.Portal>
        </Menu.Sub>
        <Menu.Sub>
          <Menu.SubTrigger class={itemClass} disabled={unavailable}>Change to layer…<ChevronRight size={14} aria-hidden="true" /></Menu.SubTrigger>
          <Menu.Portal>
            <Menu.SubContent class={menuClass} aria-label="Change to layer" sideOffset={4}>
              {#each geometry?.layer_z_mm ?? [] as _, layer (layer)}
                <Menu.Item class={itemClass} disabled={unavailable} onSelect={() => change("", String(layer))}>Layer {layer + 1}</Menu.Item>
              {/each}
            </Menu.SubContent>
          </Menu.Portal>
        </Menu.Sub>
      {/if}
    </Menu.Content>
  </Menu.Portal>
</Menu.Root>

<Dialog.Root bind:open={newCoilOpen}>
  <Dialog.Portal>
    <Dialog.Overlay class="fixed inset-0 z-[160] bg-slate-950/70" />
    <Dialog.Content class="fixed left-1/2 top-1/2 z-[161] w-80 max-w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 rounded-md border border-slate-700 bg-slate-900 p-4 text-slate-200 shadow-xl">
      <Dialog.Title class="text-sm font-semibold">Change to a new coil</Dialog.Title>
      <Dialog.Description class="mt-2 text-xs text-slate-400">Move selected segments to this coil. Their copper layers stay unchanged.</Dialog.Description>
      <form onsubmit={createCoil} class="mt-4 flex flex-col gap-3">
        <label class="text-xs">Coil name<input class="mt-1 w-full rounded border border-slate-600 bg-slate-950 p-2 focus:outline-none focus:ring-2 focus:ring-emerald-500" bind:value={coilName} /></label>
        <div class="flex justify-end gap-2 text-xs">
          <Dialog.Close class="rounded border border-slate-700 px-3 py-2">Cancel</Dialog.Close>
          <button type="submit" disabled={unavailable || !coilName.trim()} class="rounded border border-emerald-600 px-3 py-2 text-emerald-300 disabled:opacity-40">Move selection</button>
        </div>
      </form>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
