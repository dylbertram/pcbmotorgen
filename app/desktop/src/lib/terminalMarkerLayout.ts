export interface MarkerAnchor { x: number; y: number }
export interface MarkerCallout extends MarkerAnchor { labelX: number; labelY: number }

/** Screen-pixel callouts. Offset cards from copper and stack colliding labels. */
export function layoutTerminalMarkers(points: MarkerAnchor[], width: number, height: number): MarkerCallout[] {
  const placed: MarkerCallout[] = [];
  const cardWidth = 132, cardHeight = 24, gap = 6;
  for (const point of points) {
    let best = { ...point, labelX: 0, labelY: 0 };
    let bestScore = Infinity;
    for (let ring = 0; ring < Math.max(12, points.length * 2); ring++) {
      for (const side of [1, -1]) {
        const labelX = Math.max(4, Math.min(width - cardWidth - 4, point.x + (side > 0 ? 20 : -cardWidth - 20)));
        const offset = Math.ceil(ring / 2) * (ring % 2 === 0 ? -1 : 1) * (cardHeight + gap);
        const labelY = Math.max(4, Math.min(height - cardHeight - 4, point.y - 36 + offset));
        const collisions = placed.filter((p) => Math.abs(p.labelX - labelX) < cardWidth + gap && Math.abs(p.labelY - labelY) < cardHeight + gap).length;
        const coversPoint = points.some((p) => p.x >= labelX - 4 && p.x <= labelX + cardWidth + 4 && p.y >= labelY - 4 && p.y <= labelY + cardHeight + 4);
        const score = collisions * 1e6 + Number(coversPoint) * 1e4 + Math.hypot(labelX + cardWidth / 2 - point.x, labelY + cardHeight / 2 - point.y);
        if (score < bestScore) { bestScore = score; best = { ...point, labelX, labelY }; }
      }
    }
    placed.push(best);
  }
  return placed;
}
