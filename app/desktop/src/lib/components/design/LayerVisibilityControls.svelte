<script lang="ts">
  let {
    layers,
    isVisible,
    onToggle,
  }: {
    layers: { idx: number }[];
    isVisible: (layerIdx: number) => boolean;
    onToggle: (layerIdx: number) => void;
  } = $props();
</script>

{#if layers.length > 0}
  <div class="flex items-center gap-2 flex-wrap" role="group" aria-label="Layer visibility">
    {#each layers as layer (layer.idx)}
      <label
        class="flex items-center gap-1 text-xs select-none cursor-pointer"
        class:text-slate-500={!isVisible(layer.idx)}
        class:text-slate-300={isVisible(layer.idx)}
      >
        <input
          type="checkbox"
          checked={isVisible(layer.idx)}
          onchange={() => onToggle(layer.idx)}
          class="accent-emerald-500"
          aria-label={`Show layer ${layer.idx}`}
        />
        <span
          class="inline-block w-2.5 h-2.5 rounded-full"
          style={`background-color: #94a3b8; opacity: ${isVisible(layer.idx) ? 1 : 0.35}`}
        ></span>
        <span>Layer {layer.idx}</span>
      </label>
    {/each}
  </div>
{/if}
