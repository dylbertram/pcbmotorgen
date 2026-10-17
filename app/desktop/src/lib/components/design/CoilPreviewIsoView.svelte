<script lang="ts">
  /**
   * CoilPreviewIsoView.svelte — layer-aware isometric copper view.
   *
   * The top-down canvas overlays every copper layer at its true XY, so
   * overlapping traces on different Z are indistinguishable. This view
   * projects the shared CadGeometry (the same for generated and imported
   * designs) through the axonometric projection in `lib/geometry.ts`, drawing
   * each copper plane at its `layer_z_mm` height with Z exaggerated, and via
   * barrels as vertical spans between their endpoint layers. Layers are drawn
   * bottom-to-top (painter's order) so nearer copper reads on top.
   *
   * Read-only: the inline and expanded previews swap this in for the canvas
   * when `view.viewMode === "iso"`. Editing stays in the top-down view.
   */
  import type { CadGeometry, CadPoint } from "../../types";
  import { ISO_Z_EXAG, isoProject } from "../../geometry";
  import { arcSvgPath, sampleSpline } from "../../curvePaths";
  import type { CoilPreviewViewState } from "./coilPreviewViewState.svelte";
  import { PHASE_COLORS, PREVIEW_H, PREVIEW_W } from "./coilPreviewCanvas";

  let { geometry, view, isVisible = () => true }: {
    geometry: CadGeometry | null;
    view: CoilPreviewViewState;
    isVisible?: (coil: string, layer: number) => boolean;
  } = $props();

  const W = PREVIEW_W;
  const H = PREVIEW_H;
  const VIA_COLOR = "#fbbf24";

  let coilNames = $derived.by(() => {
    const names = new Set<string>();
    if (geometry) {
      for (const s of geometry.routing.segments) names.add(s.net);
      for (const c of geometry.routing.curves) names.add(c.net);
      for (const s of geometry.routing.splines ?? []) names.add(s.net);
    }
    return [...names].sort();
  });

  function colorFor(net: string): string {
    const idx = coilNames.indexOf(net);
    return PHASE_COLORS[(idx < 0 ? 0 : idx) % PHASE_COLORS.length];
  }

  let scene = $derived.by(() => {
    const g = geometry;
    const zs = g?.layer_z_mm ?? [];
    const hasCopper = !!g && (g.routing.segments.length + g.routing.curves.length
      + (g.routing.splines?.length ?? 0) + g.routing.vias.length > 0);
    if (!g || !hasCopper || zs.length === 0) return null;

    const points: CadPoint[] = [];
    for (const s of g.routing.segments) points.push(s.start, s.end);
    for (const c of g.routing.curves) points.push(c.start, c.mid, c.end);
    for (const s of g.routing.splines ?? []) points.push(...s.control_points);
    if (points.length === 0) return null;

    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const minZ = Math.min(...zs);
    const maxZ = Math.max(...zs);
    const spanX = Math.max(maxX - minX, 1e-3);
    const spanY = Math.max(maxY - minY, 1e-3);
    const spanZ = Math.max(maxZ - minZ, 0);
    const availW = W - 96;
    const availH = H - 68;
    const heightSpan = Math.max(0.45 * spanY + spanZ * ISO_Z_EXAG, 1e-6);
    const sxy = 0.9 * Math.min(availW / (spanX + 0.45 * spanY), availH / heightSpan);
    const sz = sxy * ISO_Z_EXAG;
    const project = (x: number, y: number, z: number, cx: number, cy: number) =>
      isoProject(x, y, z, cx, cy, sxy, sz);
    // Center the projected bounding hull.
    let minSx = Infinity, minSy = Infinity, maxSx = -Infinity, maxSy = -Infinity;
    for (const [x, y, z] of [[minX, minY, minZ], [maxX, minY, minZ], [maxX, maxY, minZ],
      [minX, maxY, minZ], [minX, minY, maxZ], [maxX, minY, maxZ], [maxX, maxY, maxZ], [minX, maxY, maxZ]]) {
      const [sx, sy] = project(x, y, z, 0, 0);
      minSx = Math.min(minSx, sx); maxSx = Math.max(maxSx, sx);
      minSy = Math.min(minSy, sy); maxSy = Math.max(maxSy, sy);
    }
    const cx = W / 2 - (minSx + maxSx) / 2;
    const cy = H / 2 - (minSy + maxSy) / 2;
    const at = (p: CadPoint, z: number) => project(p.x, p.y, z, cx, cy);

    const layers = zs.map((z, idx) => ({ idx, z, visible: view.isLayerVisible(idx) }))
      .sort((a, b) => a.z - b.z); // painter's order: bottom first
    const traceWidth = view.traceMode === "centerlines" ? 1 : Math.max(0.9, (g.trace_width_mm || 0.1) * sxy);

    const traces = layers.filter((l) => l.visible).map((l) => {
      const z = zs[l.idx];
      const segments = g.routing.segments.filter((s) => s.layer === l.idx && isVisible(s.net, s.layer)).map((s, i) => {
        const a = at(s.start, z), b = at(s.end, z);
        return { key: `${l.idx}-${i}`, net: s.net, x1: a[0], y1: a[1], x2: b[0], y2: b[1] };
      });
      const curves = g.routing.curves.filter((c) => c.layer === l.idx && isVisible(c.net, c.layer)).map((c, i) => {
        // Affine projection of the original circular arc produces the exact
        // ellipse. A quadratic fitted through its midpoint changes its shape.
        return { key: `${l.idx}-${i}`, net: c.net, d: arcSvgPath(c), transform: `matrix(${sxy} 0 ${0.45 * sxy} ${0.45 * sxy} ${cx} ${cy - z * sz})` };
      });
      const splines = (g.routing.splines ?? []).filter((s) => s.layer === l.idx && isVisible(s.net, s.layer)).map((s, i) => {
        const pts = sampleSpline(s, 12).map((p) => at(p, z));
        return { key: `${l.idx}-${i}-${s.net}`, net: s.net, points: pts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ") };
      });
      return { idx: l.idx, z, segments, curves, splines };
    });

    const vias = view.showVias ? g.routing.vias
      .filter((v) => (view.isLayerVisible(v.from_layer) && isVisible(v.net, v.from_layer)) || (view.isLayerVisible(v.to_layer) && isVisible(v.net, v.to_layer)))
      .map((v, i) => {
        const z0 = zs[v.from_layer] ?? 0;
        const z1 = zs[v.to_layer] ?? z0;
        const a = at(v.position, z0), b = at(v.position, z1);
        return { key: `via-${i}-${v.net}`, x1: a[0], y1: a[1], x2: b[0], y2: b[1] };
      }) : [];

    const terminals = view.showTerminals ? Object.entries(g.coil_terminals ?? {}).flatMap(([coil, t]) => {
      const z = zs[t.input.layer] ?? 0;
      const zi = zs[t.output.layer] ?? 0;
      const a = at(t.input.position, z), b = at(t.output.position, zi);
      return [
        ...(view.isLayerVisible(t.input.layer) && isVisible(coil, t.input.layer) ? [{ key: `${coil}-in`, x: a[0], y: a[1] }] : []),
        ...(view.isLayerVisible(t.output.layer) && isVisible(coil, t.output.layer) ? [{ key: `${coil}-out`, x: b[0], y: b[1] }] : []),
      ];
    }) : [];

    return { layers: traces, vias, terminals, traceWidth, netCount: coilNames.length };
  });

  let segmentCount = $derived(scene ? scene.layers.reduce((n, l) => n + l.segments.length + l.curves.length + l.splines.length, 0) : 0);
  let viaCount = $derived(scene?.vias.length ?? 0);
</script>

{#if scene}
  <svg
    viewBox="0 0 {W} {H}"
    preserveAspectRatio="xMidYMid meet"
    role="img"
    aria-label="Coil preview — isometric"
    class="block h-full w-full"
    data-testid="coil-iso"
    data-layers={scene.layers.length}
    data-segments={segmentCount}
    data-vias={viaCount}
  >
    <!-- Via barrels first so traces read over them at their own depth. -->
    {#each scene.vias as via (via.key)}
      <line x1={via.x1} y1={via.y1} x2={via.x2} y2={via.y2} stroke={VIA_COLOR} stroke-width="1.4" stroke-opacity="0.85" />
      <circle cx={via.x1} cy={via.y1} r="2.4" fill={VIA_COLOR} stroke="#0f172a" stroke-width="0.6" />
      <circle cx={via.x2} cy={via.y2} r="2.4" fill={VIA_COLOR} stroke="#0f172a" stroke-width="0.6" />
    {/each}

    {#each scene.layers as layer (layer.idx)}
      <g>
        {#each layer.segments as seg (seg.key)}
          <line x1={seg.x1} y1={seg.y1} x2={seg.x2} y2={seg.y2} stroke={colorFor(seg.net)} stroke-width={scene.traceWidth.toFixed(2)} stroke-linecap="round" />
        {/each}
        {#each layer.curves as curve (curve.key)}
          <path d={curve.d} transform={curve.transform} vector-effect="non-scaling-stroke" fill="none" stroke={colorFor(curve.net)} stroke-width={scene.traceWidth.toFixed(2)} stroke-linecap="round" />
        {/each}
        {#each layer.splines as spline (spline.key)}
          <polyline points={spline.points} fill="none" stroke={colorFor(spline.net)} stroke-width={scene.traceWidth.toFixed(2)} stroke-linecap="round" stroke-linejoin="round" />
        {/each}
      </g>
    {/each}

    {#each scene.terminals as terminal (terminal.key)}
      <circle cx={terminal.x} cy={terminal.y} r="3" fill="#34d399" stroke="#0f172a" stroke-width="0.8" />
    {/each}

    <!-- Copper-plane height legend, bottom-to-top. -->
    <g class="fill-slate-400" style="font-size:10px" font-family="ui-monospace, monospace">
      <text x={W - 8} y="14" text-anchor="end">Z × {ISO_Z_EXAG}</text>
      {#each scene.layers as layer, i (layer.idx)}
        <text x={W - 8} y={28 + i * 12} text-anchor="end">L{layer.idx + 1} · {layer.z.toFixed(2)} mm</text>
      {/each}
    </g>
  </svg>
{:else}
  <div class="flex h-full w-full items-center justify-center text-sm text-slate-500" role="img" aria-label="Coil preview — isometric">
    Awaiting coil generation…
  </div>
{/if}
