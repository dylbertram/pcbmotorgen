<script lang="ts" module>
  // How the three phase windings terminate, drawn in the style of a motor
  // wiring sheet: a terminal rail on the left, coloured leads A/B/C, and the
  // windings as looped coils. Delta joins the coils end to end round the
  // magnet; star meets one end of each at a neutral. Inline, so the tooltip
  // has nothing to load.

  const W = 172;
  const H = 158;
  const CX = 114;
  const CY = 80;
  const R = 42;
  const RAIL_X = 12;

  const INK = "#1f2937";
  const PHASE = ["#2f6fdb", "#c22f3c", "#2f9e5c"];

  type Pt = readonly [number, number];

  const at = (deg: number, radius = R): Pt => [
    CX + radius * Math.cos((deg * Math.PI) / 180),
    CY - radius * Math.sin((deg * Math.PI) / 180),
  ];

  /**
   * A winding as a looped coil (a trochoid) between two points, with a short
   * straight tail at each end. `away` turns the loops away from that point.
   */
  function coil(from: Pt, to: Pt, loops: number, away?: Pt, r = 3.2, tail = 0.18): string {
    const dx = to[0] - from[0];
    const dy = to[1] - from[1];
    const len = Math.hypot(dx, dy) || 1;
    const ux = dx / len;
    const uy = dy / len;
    let px = -uy;
    let py = ux;
    if (away) {
      const mx = (from[0] + to[0]) / 2 - away[0];
      const my = (from[1] + to[1]) / 2 - away[1];
      if (px * mx + py * my < 0) {
        px = -px;
        py = -py;
      }
    }
    const span = len * (1 - 2 * tail);
    const steps = loops * 24;
    const point = (s: number, n: number) =>
      `${(from[0] + ux * s + px * n).toFixed(2)} ${(from[1] + uy * s + py * n).toFixed(2)}`;
    const parts = [`M ${point(0, 0)}`, `L ${point(len * tail, 0)}`];
    for (let i = 1; i <= steps; i += 1) {
      const theta = (2 * Math.PI * loops * i) / steps;
      const s = len * tail + (span * i) / steps - r * Math.sin(theta);
      parts.push(`L ${point(s, r * (1 - Math.cos(theta)))}`);
    }
    parts.push(`L ${point(len, 0)}`);
    return parts.join(" ");
  }

  /** A lead from the rail at `y`, stepping once at `stepX` to reach `to`. */
  function lead(y: number, to: Pt, stepX: number, vertical = false): string {
    return vertical
      ? `M ${RAIL_X} ${y} H ${to[0].toFixed(2)} V ${to[1].toFixed(2)}`
      : `M ${RAIL_X} ${y} H ${stepX} V ${to[1].toFixed(2)} H ${to[0].toFixed(2)}`;
  }

  // Delta: joints at 120°, 240° and 0°, one coil along each side of the triangle.
  const DELTA_NODES = [at(120), at(240), at(0)];
  const DELTA = {
    nodes: DELTA_NODES,
    coils: DELTA_NODES.map((n, i) => coil(n, DELTA_NODES[(i + 1) % 3], 7, [CX, CY])),
    leads: [lead(22, DELTA_NODES[0], 0, true), lead(98, DELTA_NODES[1], 56), lead(144, DELTA_NODES[2], 0, true)],
    labelY: [22, 98, 144],
  };

  // Star: coil ends on the circle at 60°, 180° and 300°, all meeting at the centre.
  const STAR_ENDS = [at(60), at(180), at(300)];
  const STAR = {
    nodes: STAR_ENDS,
    coils: STAR_ENDS.map((n) => coil(n, [CX, CY], 5)),
    leads: [lead(22, STAR_ENDS[0], 0, true), lead(CY, STAR_ENDS[1], 0, true), lead(144, STAR_ENDS[2], 0, true)],
    labelY: [22, CY, 144],
  };
</script>

<script lang="ts">
  let { kind }: { kind: "delta" | "star" } = $props();

  const fig = $derived(kind === "delta" ? DELTA : STAR);
</script>

<svg
  viewBox={`0 0 ${W} ${H}`}
  class="wc-schematic"
  role="img"
  aria-label={kind === "delta"
    ? "Delta: the three windings join end to end in a ring round the magnet, and each joint takes one lead."
    : "Star: one end of each winding meets at a neutral, and the free ends take the leads."}
>
  <rect width={W} height={H} rx="6" fill="#fff" />

  <!-- rail -->
  <path d={`M ${RAIL_X} 8 V ${H - 6}`} stroke={INK} stroke-width="1.2" fill="none" />

  {#if kind === "star"}
    <circle cx={CX} cy={CY} r={R} fill="none" stroke={INK} stroke-width="1.3" />
  {/if}

  <!-- leads, terminals, labels -->
  {#each fig.leads as d, i (i)}
    <path {d} stroke={PHASE[i]} stroke-width="1.6" fill="none" stroke-linejoin="round" />
    <rect x={RAIL_X - 4} y={fig.labelY[i] - 4} width="8" height="8" fill="#fff" stroke={INK} stroke-width="1" />
    <text x={RAIL_X + 8} y={fig.labelY[i] - 4} font-size="10" font-weight="600" fill={PHASE[i]}>
      {["A", "B", "C"][i]}
    </text>
  {/each}

  <!-- windings -->
  {#each fig.coils as d, i (i)}
    <path {d} stroke={INK} stroke-width="1.1" fill="none" stroke-linejoin="round" />
  {/each}

  <!-- joints -->
  {#if kind === "delta"}
    {#each fig.nodes as [x, y], i (i)}
      <circle cx={x} cy={y} r="2.4" fill={INK} />
    {/each}
    <!-- magnet -->
    <circle cx={CX} cy={CY} r="11" fill="#d1d5db" stroke={INK} stroke-width="1.1" />
    <path d={`M ${CX - 7.8} ${CY + 7.8} L ${CX + 7.8} ${CY - 7.8}`} stroke={INK} stroke-width="1" />
    <text x={CX - 3.6} y={CY - 0.8} text-anchor="middle" font-size="7" font-weight="700" fill={INK}>N</text>
    <text x={CX + 3.6} y={CY + 6.6} text-anchor="middle" font-size="7" font-weight="700" fill={INK}>S</text>
  {:else}
    <circle cx={CX} cy={CY} r="2.8" fill={INK} />
  {/if}
</svg>

<style>
  .wc-schematic {
    display: block;
    width: 100%;
    height: auto;
  }
</style>
