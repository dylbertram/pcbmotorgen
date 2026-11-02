import { describe, expect, it, vi } from "vitest";
import { WorldPen } from "./worldCanvasPen";

describe("world canvas pen", () => {
  it("converts metre coordinates, lengths and dashes to canvas units", () => {
    const ctx = { moveTo: vi.fn(), lineTo: vi.fn(), arc: vi.fn(), setLineDash: vi.fn(), lineWidth: 0 };
    const pen = new WorldPen(ctx as unknown as CanvasRenderingContext2D);
    pen.moveTo(0.001, -0.002);
    pen.lineTo(0.003, 0.004);
    pen.arc(0.005, 0.006, 0.0005, 0, Math.PI);
    pen.lineWidth = 0.0002;
    pen.setLineDash([0.001, 0.002]);
    expect(ctx.moveTo).toHaveBeenCalledWith(1000, -2000);
    expect(ctx.lineTo).toHaveBeenCalledWith(3000, 4000);
    expect(ctx.arc).toHaveBeenCalledWith(5000, 6000, 500, 0, Math.PI);
    expect(ctx.lineWidth).toBe(200);
    expect(ctx.setLineDash).toHaveBeenCalledWith([1000, 2000]);
    expect(pen.point({ x: 0.001, y: -0.002 })).toEqual({ x: 1000, y: -2000 });
  });
});
