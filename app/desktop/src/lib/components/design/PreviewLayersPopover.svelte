<script lang="ts">
  import { Popover } from "bits-ui";
  import { Layers, X } from "@lucide/svelte";
  import CoilPreviewVisibilityPanel from "./CoilPreviewVisibilityPanel.svelte";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import type { CadGeometry } from "../../types";
  import type { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";

  let { view, layers, coils = [], isCoilVisible, onToggleCoil,
    label, phases = [], showMotorControls = false, hasPolePitchData = false,
    hasBandWidthData = false, hasPoleRegionData = false, poleRegionPhases = [], geometry, selection, assignmentDisabled = false }: {
    view: CoilPreviewViewState;
    layers: { idx: number }[];
    coils?: { name: string; colorIdx: number }[];
    isCoilVisible?: (name: string) => boolean;
    onToggleCoil?: (name: string) => void;
    label: string;
    phases?: { idx: number; name: string; colorIdx: number }[];
    showMotorControls?: boolean;
    hasPolePitchData?: boolean;
    hasBandWidthData?: boolean;
    hasPoleRegionData?: boolean;
    poleRegionPhases?: string[];
    geometry?: CadGeometry | null;
    selection?: CadSelectionTool;
    assignmentDisabled?: boolean;
  } = $props();
</script>

<div role="toolbar" aria-label="Preview side tools" aria-orientation="vertical" class="absolute inset-y-0 right-0 flex w-11 flex-col items-center gap-2 border-l border-slate-700 bg-slate-900 py-2">
<Popover.Root>
  <Popover.Trigger aria-label="Layers" class="flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-slate-300 hover:bg-slate-800 data-[state=open]:border-emerald-500 data-[state=open]:text-emerald-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500" title="Show or hide preview layers and coils.">
    <Layers size={16} aria-hidden="true" />
  </Popover.Trigger>
  <Popover.Portal>
    <Popover.Content side="left" align="start" sideOffset={8} role="dialog" aria-label={label}
      class="z-[130] flex max-h-[min(32rem,var(--bits-popover-content-available-height))] w-60 max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-md border border-slate-700 bg-slate-900 text-slate-200 shadow-xl shadow-black/40">
      <header class="flex shrink-0 items-center justify-between border-b border-slate-700 px-3 py-2">
        <h3 class="text-sm font-semibold">Layers</h3>
        <Popover.Close aria-label="Close layers panel" class="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500">
          <X size={16} aria-hidden="true" />
        </Popover.Close>
      </header>
      <div class="min-h-0 overflow-y-auto overscroll-contain p-3">
        <CoilPreviewVisibilityPanel {view} uniqueLayers={layers} uniquePhases={phases} {coils} {isCoilVisible} {onToggleCoil}
          {showMotorControls} {hasPolePitchData} {hasBandWidthData} {hasPoleRegionData} {poleRegionPhases} {geometry} {selection} {assignmentDisabled} />
      </div>
    </Popover.Content>
  </Popover.Portal>
</Popover.Root>
</div>
