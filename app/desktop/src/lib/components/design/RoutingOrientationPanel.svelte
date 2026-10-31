<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { CadGeometry } from "../../types";
  import { DEFAULT_ROUTING_ORIENTATION, flipCadGeometry, type RoutingFlip } from "../../routingOrientation";

  let { config, geometry = null, onGeometryChange }: {
    config: ConfigStore;
    geometry?: CadGeometry | null;
    onGeometryChange?: (geometry: CadGeometry) => void;
  } = $props();
  const flips: { key: RoutingFlip; label: string; help: string }[] = [
    { key: "mirror_x", label: "Mirror left/right (X)", help: "Reflect copper across the vertical plane. Move input leads to the opposite X side." },
    { key: "mirror_y", label: "Mirror up/down (Y)", help: "Reflect copper across the horizontal plane. Move input leads to the opposite Y side." },
    { key: "reverse_layers", label: "Reverse layers (Z)", help: "Swap top and bottom. Reverse all copper layers, via spans, terminals, and the stackup." },
  ];
  function toggle(key: RoutingFlip) {
    if (geometry) {
      if (!onGeometryChange) return;
      onGeometryChange(flipCadGeometry($state.snapshot(geometry), { ...DEFAULT_ROUTING_ORIENTATION, [key]: true }));
      if (key === "reverse_layers") config.reversePcbStackup();
      return;
    }
    config.toggleRoutingFlip(key);
  }
</script>

<fieldset class="border-t border-slate-700 pt-3" aria-label="Routing orientation">
  <legend class="mb-2 pr-2 text-xs font-medium text-slate-300">Orientation</legend>
  <div class="grid gap-1.5">
    {#each flips as flip (flip.key)}
      <label class="flex min-h-8 items-center gap-2 text-xs text-slate-200" title={flip.help}>
        <input type="checkbox" class="accent-emerald-400"
          checked={geometry ? geometry.applied_orientation?.[flip.key] ?? false : config.routing_orientation[flip.key]}
          disabled={!!geometry && !onGeometryChange} onchange={() => toggle(flip.key)} />
        {flip.label}
      </label>
    {/each}
  </div>
</fieldset>
