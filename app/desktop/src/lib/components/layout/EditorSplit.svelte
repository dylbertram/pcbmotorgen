<script lang="ts">
  import type { Snippet } from "svelte";
  import type { AnalysisWorkspace } from "../../stores/analysisWorkspace.svelte";

  let { state, left, right }: { state: AnalysisWorkspace; left: Snippet; right: Snippet } = $props();
  let frame: HTMLDivElement;
  let pointer: number | null = null;

  function resize(event: PointerEvent): void {
    if (pointer !== event.pointerId) return;
    const bounds = frame.getBoundingClientRect();
    if (bounds.width >= 768) state.resize((event.clientX - bounds.left) / bounds.width * 100);
  }
  function release(event: PointerEvent): void {
    if (pointer !== event.pointerId) return;
    pointer = null;
    const node = event.currentTarget as HTMLElement;
    if (node.hasPointerCapture(event.pointerId)) node.releasePointerCapture(event.pointerId);
  }
  function keyResize(event: KeyboardEvent): void {
    const next = { ArrowLeft: state.leftPercent - 3, ArrowRight: state.leftPercent + 3, Home: 30, End: 75 }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    state.resize(next);
  }
</script>

<div bind:this={frame} class="editor-split min-h-0 min-w-0 flex-1" class:split={state.driverCheckOpen}
  style:--split-left={`${state.leftPercent}fr`} style:--split-right={`${100 - state.leftPercent}fr`}>
  <div class="flex min-h-0 min-w-0 flex-col" onpointerdowncapture={() => { state.focusedGroup = "design"; }} onfocusincapture={() => { state.focusedGroup = "design"; }}>
    {@render left()}
  </div>
  {#if state.driverCheckOpen}
    <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
    <div role="separator" aria-label="Resize editor groups" aria-orientation="vertical" tabindex="0"
      aria-valuemin="30" aria-valuemax="75" aria-valuenow={Math.round(state.leftPercent)}
      class="splitter bg-slate-700 hover:bg-emerald-500 focus-visible:bg-emerald-500 focus-visible:outline-none"
      onpointerdown={(event) => { if (event.button !== 0) return; pointer = event.pointerId; event.currentTarget.setPointerCapture(pointer); event.preventDefault(); }}
      onpointermove={resize} onpointerup={release} onpointercancel={release} onlostpointercapture={() => { pointer = null; }} onkeydown={keyResize} ondblclick={() => state.resize(50)}></div>
    <div class="flex min-h-0 min-w-0 flex-col" onpointerdowncapture={() => { state.focusedGroup = "driver"; }} onfocusincapture={() => { state.focusedGroup = "driver"; }}>
      {@render right()}
    </div>
  {/if}
</div>

<style>
  .editor-split { display: grid; grid-template-columns: minmax(0, 1fr); }
  .split { grid-template-columns: minmax(0, var(--split-left)) 5px minmax(0, var(--split-right)); }
  .splitter { touch-action: none; cursor: col-resize; }
  @media (max-width: 767px) {
    .split { grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(140px, 1fr) 5px minmax(140px, 1fr); }
    .splitter { cursor: default; }
  }
</style>
