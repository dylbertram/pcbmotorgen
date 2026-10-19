<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { TraceMeasure } from "../../previewGeometry";
  import {
    ISO_Z_EXAG,
    isoBoxPath,
    isoCenter as computeIsoCenter,
    isoProject,
  } from "../../geometry";

  let {
    config,
    measuredTrace = null,
    stripStartMm,
    stripEndMm,
  }: {
    config: ConfigStore;
    /** Measured payload geometry; null falls back to configured numbers. */
    measuredTrace?: TraceMeasure | null;
    /** Mover strip extent in the DOMAIN frame (canvas-anchored). */
    stripStartMm: number;
    stripEndMm: number;
  } = $props();

  // ====================================================================
  // 3/4 ISOMETRIC VIEW — axonometric projection of the assembly (PCB
  // wireframe + magnet wireframe). Z is exaggerated so the thin stackup
  // is visible. The magnet block sits at the current mover position
  // along the travel axis.
  //
  // Everything is drawn in the ROUTING/DOMAIN frame — the same frame the
  // coil canvas uses: x = 0 is the left edge of the routed traces and of
  // the copper active region — the routing domain equals the active area.
  // The board length is the MEASURED trace span when a payload exists
  // (the braid floors whole periods, so it is shorter than the nominal
  // domain).
  // ====================================================================
  const ISO_W = 360;
  const ISO_H = 130;
  const ISO_PAD = 14;

  let boardLengthMm = $derived(
    measuredTrace?.traceLengthMm ?? config.trace_total_length_mm,
  );
  let boardStartMm = $derived(measuredTrace?.traceStartMm ?? 0);

  let isoScale = $derived(
    (ISO_W - 2 * ISO_PAD) / Math.max(boardLengthMm * 1.45, 1),
  );

  // Axonometric projection (delegates to the shared lib/geometry helper
  // with the Z-exaggerated scale baked in):
  //     sx = cx + (x + 0.45·y) · sXY
  //     sy = cy + (-z·Z_EXAG + 0.45·y) · sXY
  const project = (
    x: number, y: number, z: number, cx: number, cy: number,
  ): [number, number] => isoProject(x, y, z, cx, cy, isoScale, isoScale * ISO_Z_EXAG);

  // Center the assembly's bounding box in the iso canvas.
  let isoCenter = $derived(
    computeIsoCenter(
      {
        length: boardLengthMm,
        width: config.active_area_width_mm,
        totalHeight:
          config.pcb_thickness_mm +
          config.air_gap_mm +
          config.magnet_height_mm,
      },
      ISO_W,
      ISO_H,
      project,
    ),
  );

  let isoGeom = $derived.by(() => {
    const pcbT = config.pcb_thickness_mm;
    const ag = config.air_gap_mm;
    const mh = config.magnet_height_mm;
    return {
      boardX0: boardStartMm,
      boardL: boardLengthMm,
      // Copper active region (domain frame).
      activeX0: 0,
      activeL: config.active_area_length_mm,
      W: config.active_area_width_mm,
      pcbT,
      ag,
      mh,
      // Z-stack (stator at z=0, then PCB → air gap → magnet).
      pcbZTop: pcbT,
      airGapZBottom: pcbT,
      magnetZBottom: pcbT + ag,
      // Mover strip extent (domain frame, canvas-anchored + motion offset).
      magnetStartX: stripStartMm,
      magnetEndX: stripEndMm,
    };
  });

  // Pre-computed wireframe boxes for the iso view.
  let isoStatorBox = $derived(
    isoBoxPath(isoGeom.boardX0, 0, 0, isoGeom.boardL, isoGeom.W, isoGeom.pcbT, isoCenter.cx, isoCenter.cy, project),
  );
  // Flat outline of the copper ACTIVE region on the PCB top face: the
  // mover's strip stays within this region at both travel endpoints.
  let isoActiveBox = $derived(
    isoBoxPath(isoGeom.activeX0, 0, isoGeom.pcbT, isoGeom.activeL, isoGeom.W, 0.01, isoCenter.cx, isoCenter.cy, project),
  );
  let isoMagnetBox = $derived(
    isoBoxPath(isoGeom.magnetStartX, 0, isoGeom.magnetZBottom,
      isoGeom.magnetEndX - isoGeom.magnetStartX, isoGeom.W, isoGeom.mh,
      isoCenter.cx, isoCenter.cy, project),
  );

  // Dimension line under the board's front-bottom edge: ties the printed
  // "routed traces" number to the drawn span (measured when a payload exists).
  let isoDim = $derived.by(() => {
    const [x1, y1] = project(isoGeom.boardX0, 0, 0, isoCenter.cx, isoCenter.cy);
    const [x2, y2] = project(isoGeom.boardX0 + isoGeom.boardL, 0, 0, isoCenter.cx, isoCenter.cy);
    const y = Math.max(y1, y2) + 9;
    return { x1, x2, y };
  });
</script>

<div class="min-w-0">
  <svg viewBox="0 0 {ISO_W} {ISO_H}" class="h-36 w-full"
       role="img" aria-label="Three-quarter isometric view of the assembly">
    <!-- Stator (PCB) wireframe box: MEASURED routed-trace extent -->
    <path d={isoStatorBox.d} fill="#1e293b" fill-opacity="0.35" stroke="#94a3b8" stroke-width="1" />

    <!-- Dimension line: routed-trace span (measured from the payload) -->
    <g class="text-slate-400" stroke="currentColor" stroke-width="0.7">
      <line x1={isoDim.x1} y1={isoDim.y} x2={isoDim.x2} y2={isoDim.y} />
      <line x1={isoDim.x1} y1={isoDim.y - 3} x2={isoDim.x1} y2={isoDim.y + 3} />
      <line x1={isoDim.x2} y1={isoDim.y - 3} x2={isoDim.x2} y2={isoDim.y + 3} />
      <text x={(isoDim.x1 + isoDim.x2) / 2} y={isoDim.y + 9} text-anchor="middle"
            class="fill-slate-400" stroke="none" style="font-size:8px"
            >routed traces {boardLengthMm.toFixed(1)} mm{measuredTrace ? " ·meas." : ""}</text>
    </g>

    <!-- Copper active-region outline on the PCB top face -->
    <path d={isoActiveBox.d} fill="none" stroke="#34d399" stroke-width="0.8" stroke-dasharray="3 2" />

    <!-- Magnet array wireframe box (positioned by the mover-position field) -->
    <path d={isoMagnetBox.d} fill="#065f46" fill-opacity="0.35" stroke="#10b981" stroke-width="1" />
    <text x={(isoMagnetBox.corners[4][0] + isoMagnetBox.corners[5][0]) / 2}
          y={isoMagnetBox.corners[4][1] - 4} text-anchor="middle"
          class="fill-emerald-300" style="font-size:9px">Magnets</text>

    <!-- Axis legend (bottom-left corner) -->
    <g style="font-size:8px" stroke-linecap="round">
      <!-- X axis: right (red) -->
      <line x1="20" y1={ISO_H - 22} x2="38" y2={ISO_H - 22} stroke="#ef4444" stroke-width="1.4" />
      <text x="40" y={ISO_H - 19} class="fill-red-300">X</text>
      <!-- Y axis: diagonal down-right (green) -->
      <line x1="20" y1={ISO_H - 22} x2="33" y2={ISO_H - 14} stroke="#22c55e" stroke-width="1.4" />
      <text x="34" y={ISO_H - 10} class="fill-green-300">Y</text>
      <!-- Z axis: up (blue) -->
      <line x1="20" y1={ISO_H - 22} x2="20" y2={ISO_H - 40} stroke="#3b82f6" stroke-width="1.4" />
      <text x="23" y={ISO_H - 40} class="fill-blue-300">Z</text>
    </g>
  </svg>
</div>
