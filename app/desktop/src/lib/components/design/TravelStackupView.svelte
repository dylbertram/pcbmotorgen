<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import {
    HOUSING_MATERIAL_OPTIONS,
    layerMaterialLabel,
    type BackplaneStack,
  } from "../../types/backplane";

  let { config }: { config: ConfigStore } = $props();

  // ====================================================================
  // FRONT-ON ORTHOGRAPHIC VIEW (Y–Z cross-section)
  // Every part spans the full width of the view. All thicknesses share one
  // uniform scale, so the stack is drawn to scale. That scale fits the
  // whole stack inside the view height, so px per mm depends on the total.
  // Stack from the bottom up: housing wall, housing gap, backplane layers
  // (layer 1 touches the PCB, so it sits highest), PCB, air gap, magnet.
  // ====================================================================
  const ORTHO_W = 180;
  const ORTHO_H = 160;
  const ORTHO_PAD_L = 8;
  const ORTHO_PAD_R = 54; // reserved for the height-dimension labels
  const ORTHO_PAD_T = 20;
  const ORTHO_PAD_B = 16;
  const RECT_W = ORTHO_W - ORTHO_PAD_L - ORTHO_PAD_R;
  const DIM_X = ORTHO_W - 4;
  const BASE_Y = ORTHO_H - ORTHO_PAD_B;
  // Segments shorter than this get no text inside.
  const MIN_INSIDE_LABEL_PX = 14;
  // Right-side labels are pushed apart by at least this much.
  const MIN_DIM_LABEL_GAP_PX = 13;

  type SegmentKind = "housing" | "housing-gap" | "layer" | "pcb" | "air-gap" | "magnet";

  /** One slab of the stack. Thickness in mm. */
  interface Part {
    key: string;
    kind: SegmentKind;
    mm: number;
    inside?: string;
  }

  interface Segment extends Part {
    /** SVG y of the top and bottom edges. */
    top: number;
    bottom: number;
  }

  const SEGMENT_STYLE: Record<SegmentKind, { fill: string; stroke: string; text: string }> = {
    // One neutral fill for every backplane layer; the material name is drawn inside.
    layer: { fill: "rgb(var(--slate-700))", stroke: "#64748b", text: "fill-slate-100" },
    housing: { fill: "rgba(56,189,248,0.18)", stroke: "#38bdf8", text: "fill-slate-100" },
    pcb: { fill: "rgb(var(--slate-800))", stroke: "#475569", text: "fill-slate-200" },
    "air-gap": { fill: "rgba(100,116,139,0.15)", stroke: "#475569", text: "" },
    "housing-gap": { fill: "rgba(100,116,139,0.15)", stroke: "#475569", text: "" },
    magnet: { fill: "rgba(16,185,129,0.45)", stroke: "#10b981", text: "fill-slate-100" },
  };

  /** Parts from the bottom up. Zero-thickness gaps are left out. */
  function stackParts(
    backplane: BackplaneStack | null,
    pcbMm: number,
    airGapMm: number,
    magnetMm: number,
  ): Part[] {
    const parts: Part[] = [];
    const housing = backplane?.housing ?? null;
    if (housing) {
      parts.push({
        key: "housing",
        kind: "housing",
        mm: housing.thickness_m * 1e3,
        inside: HOUSING_MATERIAL_OPTIONS.find((o) => o.value === housing.material)?.label,
      });
      if (housing.gap_m > 0) {
        parts.push({ key: "housing-gap", kind: "housing-gap", mm: housing.gap_m * 1e3 });
      }
    }
    // Layer 1 touches the PCB, so walk the list from the last layer up.
    const layers = backplane?.layers ?? [];
    for (let i = layers.length - 1; i >= 0; i--) {
      parts.push({
        key: `layer-${i}`,
        kind: "layer",
        mm: layers[i].thickness_m * 1e3,
        inside: layerMaterialLabel(layers[i].material),
      });
    }
    parts.push({ key: "pcb", kind: "pcb", mm: pcbMm, inside: "PCB" });
    if (airGapMm > 0) parts.push({ key: "air-gap", kind: "air-gap", mm: airGapMm });
    parts.push({ key: "magnet", kind: "magnet", mm: magnetMm, inside: "N · S" });
    return parts;
  }

  let parts = $derived(
    stackParts(config.backplane, config.pcb_thickness_mm, config.air_gap_mm, config.magnet_height_mm),
  );
  let totalMm = $derived(parts.reduce((sum, part) => sum + part.mm, 0));
  // One scale for every part, fitted between the top and bottom padding.
  let zScale = $derived((ORTHO_H - ORTHO_PAD_T - ORTHO_PAD_B) / Math.max(totalMm, 0.1));

  // Returned top to bottom. Each part's top edge is where the part above it ends.
  let segments = $derived.by(() => {
    let edge = BASE_Y;
    const bottomUp: Segment[] = parts.map((part) => {
      const segment = { ...part, bottom: edge, top: edge - part.mm * zScale };
      edge = segment.top;
      return segment;
    });
    return bottomUp.reverse();
  });

  // Right-side labels sit at each segment's middle. They are pushed apart
  // so that thin segments do not overlap.
  let dimLabelY = $derived(
    spreadApart(
      segments.map((s) => (s.top + s.bottom) / 2 + 2.5),
      MIN_DIM_LABEL_GAP_PX,
      ORTHO_H - 3,
    ),
  );
  // A tick at every segment top, plus the base.
  let tickY = $derived([...segments.map((s) => s.top), BASE_Y]);

  /** Thickness label with three significant figures, so 0.35 mm does not read as 0.4. */
  function fmtMm(mm: number): string {
    return String(Number(mm.toPrecision(3)));
  }

  /** Push labels apart from the top down. Then pull the bottom one back up if it runs past maxY. */
  function spreadApart(ys: number[], gap: number, maxY: number): number[] {
    const out = [...ys];
    for (let i = 1; i < out.length; i++) out[i] = Math.max(out[i], out[i - 1] + gap);
    for (let i = out.length - 1; i >= 0; i--) {
      const limit = i === out.length - 1 ? maxY : out[i + 1] - gap;
      out[i] = Math.min(out[i], limit);
    }
    return out;
  }
</script>

<div class="min-w-0">
  <div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">
    Front view (Y–Z)
  </div>
  <svg viewBox="0 0 {ORTHO_W} {ORTHO_H}" class="w-full h-auto"
       role="img" aria-label="Front-on orthographic Y–Z cross-section of the height stack, drawn to scale">
    {#each segments as seg (seg.key)}
      {@const look = SEGMENT_STYLE[seg.kind]}
      {@const h = seg.bottom - seg.top}
      <rect x={ORTHO_PAD_L} y={seg.top} width={RECT_W} height={h}
            fill={look.fill} stroke={look.stroke} stroke-width="0.6" />
      {#if seg.inside && h >= MIN_INSIDE_LABEL_PX}
        <text x={ORTHO_PAD_L + RECT_W / 2} y={seg.top + h / 2 + 2.5} text-anchor="middle"
               class={look.text} style="font-size:10px">{seg.inside}</text>
      {/if}
    {/each}

    <!-- Dimension line: from the base up to the top of the magnet -->
    <g stroke="#94a3b8" stroke-width="0.5">
      <line x1={DIM_X} y1={BASE_Y} x2={DIM_X} y2={ORTHO_PAD_T} />
      {#each tickY as y, i (i)}
        <line x1={DIM_X - 2} y1={y} x2={DIM_X + 2} y2={y} />
      {/each}
    </g>
    {#each segments as seg, i (seg.key)}
      <text x={DIM_X - 4} y={dimLabelY[i]} text-anchor="end"
             class="fill-slate-300" style="font-size:10px">
        {fmtMm(seg.mm)} mm
      </text>
    {/each}
    <text x={DIM_X - 4} y={ORTHO_PAD_T - 3} text-anchor="end"
           class="fill-slate-200 font-semibold" style="font-size:10px">
      Total: {fmtMm(totalMm)} mm
    </text>
  </svg>
</div>
