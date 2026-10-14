<script lang="ts">
  import type { CadGeometry } from "../../types";
  import type { WorldTransform } from "../../chart";
  import type { CadSelectionTool } from "../../utils/cadSelectionTool.svelte";
  import type { CoilTerminalTool } from "../../utils/coilTerminalTool.svelte";
  import CadSelectionOverlay from "./CadSelectionOverlay.svelte";
  import CoilTerminalOverlay from "./CoilTerminalOverlay.svelte";

  let { geometry, selection, terminalTool, transform, panX, panY, width, height,
    worldScale = 1, isVisible, disabled = false }: {
    geometry: CadGeometry;
    selection: CadSelectionTool;
    terminalTool?: CoilTerminalTool;
    transform: WorldTransform;
    panX: number; panY: number; width: number; height: number;
    worldScale?: number;
    isVisible: (coil: string, layer: number) => boolean;
    disabled?: boolean;
  } = $props();
</script>

<CoilTerminalOverlay {geometry} tool={terminalTool} {transform} {panX} {panY} {width} {height} {worldScale} {isVisible} />
<CadSelectionOverlay {geometry} tool={selection} {transform} {panX} {panY} {width} {height} {worldScale} {isVisible} disabled={disabled || terminalTool?.active} />
