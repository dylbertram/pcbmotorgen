<script lang="ts">
  import type { CadGeometry } from "../../types";
  import type { WorldTransform } from "../../geometry/viewport";
  import type { joinCadPreviewEndpoints } from "../../cad/cadPreview";
  import type { CoilPreviewViewState } from "../../preview/coilPreviewViewState.svelte";
  import { arcSvgPath, splineSvgPath } from "../../geometry/curvePaths";

  let { geometry, joined, view, width, height, transform, panX, panY, renderedStrokeWidth,
    previewStrokeWidth, viaPadRadius, viaDrillRadius, traceVisible, coilColor }: {
    geometry: CadGeometry;
    joined: ReturnType<typeof joinCadPreviewEndpoints>;
    view: CoilPreviewViewState;
    width: number;
    height: number;
    transform: WorldTransform;
    panX: number;
    panY: number;
    renderedStrokeWidth: number;
    previewStrokeWidth: number;
    viaPadRadius: number;
    viaDrillRadius: number;
    traceVisible: (coil: string, layer: number) => boolean;
    coilColor: (coil: string) => string;
  } = $props();

  let visibleVias = $derived(geometry.routing.vias.filter(
    (via) => traceVisible(via.net, via.from_layer) || traceVisible(via.net, via.to_layer),
  ));
</script>

<svg viewBox={`0 0 ${width} ${height}`} aria-hidden="true" preserveAspectRatio="xMidYMid meet" class="block h-full w-full">
  <g transform={`matrix(${transform.s} 0 0 ${-transform.s} ${transform.tx + panX} ${transform.ty + panY})`}>
    {#each geometry.layer_z_mm as _, layer (layer)}
      {#if view.isLayerVisible(layer)}
        <g fill="none" stroke-width={renderedStrokeWidth} stroke-linecap="round" stroke-linejoin="round">
          {#each joined.segments.filter((segment) => segment.layer === layer && traceVisible(segment.net, layer)) as segment (segment)}
            <path stroke={coilColor(segment.net)} d={`M ${segment.start.x} ${segment.start.y} L ${segment.end.x} ${segment.end.y}`} />
          {/each}
          {#each joined.curves.filter((curve) => curve.layer === layer && traceVisible(curve.net, layer)) as curve (curve)}
            <path stroke={coilColor(curve.net)} d={arcSvgPath(curve)} />
          {/each}
          {#each (geometry.routing.splines ?? []).filter((spline) => spline.layer === layer && traceVisible(spline.net, layer)) as spline (spline)}
            <path stroke={coilColor(spline.net)} d={splineSvgPath(spline)} />
          {/each}
        </g>
      {/if}
    {/each}
    {#if view.showVias}
      <g fill="#fbbf24" stroke="#0f172a" stroke-width={previewStrokeWidth * 0.25}>
        {#each visibleVias as via (via)}
          <circle fill={coilColor(via.net)} cx={via.position.x} cy={via.position.y} r={viaPadRadius} />
        {/each}
      </g>
      <g fill="#020617" stroke="#0f172a" stroke-width={previewStrokeWidth * 0.2}>
        {#each visibleVias as via (via)}
          <circle cx={via.position.x} cy={via.position.y} r={viaDrillRadius} />
        {/each}
      </g>
    {/if}
  </g>
</svg>
