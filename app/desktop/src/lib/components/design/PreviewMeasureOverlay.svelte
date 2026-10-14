<script lang="ts">
  import type { CoilPreviewMeasure } from "../../utils/coilPreviewMeasure.svelte";
  import type { WorldTransform } from "../../chart";
  import { computeMeasureRuler, formatMetresMm, type Point2D } from "../../previewGeometry";

  let { measure, transform, panX, panY, width, height, metresToWorld = 1 }: {
    measure: CoilPreviewMeasure;
    transform: WorldTransform;
    panX: number; panY: number; width: number; height: number;
    metresToWorld?: number;
  } = $props();
  function screen(p: Point2D) {
    return { x: p.x * metresToWorld * transform.s + transform.tx + panX, y: -p.y * metresToWorld * transform.s + transform.ty + panY };
  }
  let ruler = $derived(measure.mode && measure.p1 && (measure.p2 ?? measure.cursor)
    ? computeMeasureRuler(measure.p1, (measure.p2 ?? measure.cursor)!) : null);
  let start = $derived(measure.p1 ? screen(measure.p1) : null);
  let end = $derived(ruler ? screen(ruler.p2) : null);
</script>

{#if measure.mode && start}
  <svg class="pointer-events-none absolute inset-0 h-full w-full" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={ruler ? `Measurement ${formatMetresMm(ruler.mm / 1000)}` : "Measurement start"}>
    <circle cx={start.x} cy={start.y} r="3" fill="#f472b6" />
    {#if end && ruler}
      <line x1={start.x} y1={start.y} x2={end.x} y2={end.y} stroke="#f472b6" stroke-width="1.5" />
      <circle cx={end.x} cy={end.y} r="3" fill="#f472b6" />
      <text x={(start.x + end.x) / 2} y={(start.y + end.y) / 2 - 10} text-anchor="middle" fill="#f9a8d4" stroke="#020617" stroke-width="3" paint-order="stroke" font-size="12">{formatMetresMm(ruler.mm / 1000)}</text>
    {/if}
  </svg>
{/if}
