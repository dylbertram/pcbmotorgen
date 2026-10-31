<script lang="ts">
  import { onDestroy } from "svelte";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import { applyViewMenuAction, viewMenuItems } from "../../viewMenu";
  import { nativeViewMenu } from "../../viewMenuController";

  let { view, active, hasPolePitchData, hasBandWidthData, hasPoleRegionData, onFitExtents, onToggleZoomWindow }: {
    view: CoilPreviewViewState; active: boolean;
    hasPolePitchData: boolean; hasBandWidthData: boolean; hasPoleRegionData: boolean;
    onFitExtents: () => void; onToggleZoomWindow: () => void;
  } = $props();
  const connection = nativeViewMenu.connect(
    () => viewMenuItems(view, { active, polePitch: hasPolePitchData, bandWidths: hasBandWidthData, poleRegions: hasPoleRegionData }),
    (id) => applyViewMenuAction(view, id, { fitExtents: onFitExtents, toggleZoomWindow: onToggleZoomWindow }),
  );
  $effect(() => connection.update());
  onDestroy(connection.dispose);
</script>
