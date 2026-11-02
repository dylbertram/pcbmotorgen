<script lang="ts">
  import type { CadGeometry } from "../../types";
  import type { WorldTransform } from "../../chart";
  import type { CadSelectionTool } from "../../cad/cadSelectionTool.svelte";
  import type { CoilTerminalTool } from "../../cad/coilTerminalTool.svelte";
  import CadSelectionOverlay from "./CadSelectionOverlay.svelte";
  import CoilTerminalOverlay from "../winding/CoilTerminalOverlay.svelte";

  let { geometry, selection, terminalTool, transform, panX, panY, width, height,
    worldScale = 1, isVisible, disabled = false, showTerminals = true, markerRightInset = 0, renderTerminals = true }: {
    geometry: CadGeometry;
    selection: CadSelectionTool;
    terminalTool?: CoilTerminalTool;
    transform: WorldTransform;
    panX: number; panY: number; width: number; height: number;
    worldScale?: number;
    isVisible: (coil: string, layer: number) => boolean;
    disabled?: boolean;
    showTerminals?: boolean;
    markerRightInset?: number;
    renderTerminals?: boolean;
  } = $props();
</script>

{#if renderTerminals}<CoilTerminalOverlay {geometry} tool={terminalTool} {transform} {panX} {panY} {width} {height} {worldScale} {isVisible} showMarkers={showTerminals} rightInset={markerRightInset} />{/if}
<CadSelectionOverlay {geometry} tool={selection} {transform} {panX} {panY} {width} {height} {worldScale} {isVisible} disabled={disabled || terminalTool?.active} />
