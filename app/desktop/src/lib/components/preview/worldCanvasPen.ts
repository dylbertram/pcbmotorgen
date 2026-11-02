/**
 * WebKit can mis-rasterise metre-scale coordinates under large transforms.
 * Draw in micrometres and apply the reciprocal scale to the canvas transform.
 */
export const WORLD_UNITS = 1e6;

/** Canvas facade for world-metre drawing. */
export class WorldPen {
  constructor(private readonly ctx: CanvasRenderingContext2D) {}
  set strokeStyle(v: string) { this.ctx.strokeStyle = v; }
  set fillStyle(v: string) { this.ctx.fillStyle = v; }
  set globalAlpha(v: number) { this.ctx.globalAlpha = v; }
  set lineCap(v: CanvasLineCap) { this.ctx.lineCap = v; }
  set lineJoin(v: CanvasLineJoin) { this.ctx.lineJoin = v; }
  set lineWidth(v: number) { this.ctx.lineWidth = v * WORLD_UNITS; }
  setLineDash(d: number[]) { this.ctx.setLineDash(d.map((v) => v * WORLD_UNITS)); }
  beginPath() { this.ctx.beginPath(); }
  moveTo(x: number, y: number) { this.ctx.moveTo(x * WORLD_UNITS, y * WORLD_UNITS); }
  lineTo(x: number, y: number) { this.ctx.lineTo(x * WORLD_UNITS, y * WORLD_UNITS); }
  arc(x: number, y: number, r: number, a0: number, a1: number) {
    this.ctx.arc(x * WORLD_UNITS, y * WORLD_UNITS, r * WORLD_UNITS, a0, a1);
  }
  rect(x: number, y: number, w: number, h: number) {
    this.ctx.rect(x * WORLD_UNITS, y * WORLD_UNITS, w * WORLD_UNITS, h * WORLD_UNITS);
  }
  roundRect(x: number, y: number, w: number, h: number, r: number) {
    this.ctx.roundRect(x * WORLD_UNITS, y * WORLD_UNITS, w * WORLD_UNITS, h * WORLD_UNITS, r * WORLD_UNITS);
  }
  fillRect(x: number, y: number, w: number, h: number) {
    this.ctx.fillRect(x * WORLD_UNITS, y * WORLD_UNITS, w * WORLD_UNITS, h * WORLD_UNITS);
  }
  strokeRect(x: number, y: number, w: number, h: number) {
    this.ctx.strokeRect(x * WORLD_UNITS, y * WORLD_UNITS, w * WORLD_UNITS, h * WORLD_UNITS);
  }
  fill() { this.ctx.fill(); }
  stroke(path?: Path2D) { if (path) this.ctx.stroke(path); else this.ctx.stroke(); }
  /** A world point in canvas units, for building Path2D strings. */
  point(p: { x: number; y: number }) { return { x: p.x * WORLD_UNITS, y: p.y * WORLD_UNITS }; }
}
