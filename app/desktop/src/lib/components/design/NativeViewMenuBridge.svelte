<script lang="ts">
  import { onDestroy } from "svelte";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import { applyViewMenuAction, viewMenuItems } from "../../viewMenu";
  import { nativeViewMenu } from "../../viewMenuController";

  let { view, active, hasPolePitchData, hasBandWidthData, hasPoleRegionData }: {
    view: CoilPreviewViewState; active: boolean;
    hasPolePitchData: boolean; hasBandWidthData: boolean; hasPoleRegionData: boolean;
  } = $props();
  const connection = nativeViewMenu.connect(
    () => viewMenuItems(view, { active, polePitch: hasPolePitchData, bandWidths: hasBandWidthData, poleRegions: hasPoleRegionData }),
    (id) => applyViewMenuAction(view, id),
  );
  $effect(() => connection.update());
  onDestroy(connection.dispose);
</script>
