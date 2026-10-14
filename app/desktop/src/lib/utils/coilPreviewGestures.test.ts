import { describe, it, expect } from "vitest";
import {
  clampZoom,
  formatZoom,
  nextZoomStepUp,
  nextZoomStepDown,
  CoilPreviewGestures,
  type CoilPreviewGesturesOptions,
} from "./coilPreviewGestures.svelte";

const STEPS = [0.5, 1, 1.5, 2, 3, 4, 6, 8, 10];

function makeGestures(
  overrides: Partial<CoilPreviewGesturesOptions> = {},
): CoilPreviewGestures {
  return new CoilPreviewGestures({
    virtualW: 760,
    virtualH: 260,
    minZoom: 0.5,
    maxZoom: 10,
    zoomSteps: STEPS,
    getWorldTransform: (zoom) => ({ s: zoom, tx: 0, ty: 0 }),
    ...overrides,
  });
}

describe("clampZoom", () => {
  it("clamps below the minimum and above the maximum", () => {
    expect(clampZoom(0.1, 0.5, 10)).toBe(0.5);
    expect(clampZoom(42, 0.5, 10)).toBe(10);
  });

  it("passes values inside the range through unchanged", () => {
    expect(clampZoom(1, 0.5, 10)).toBe(1);
    expect(clampZoom(6, 0.5, 10)).toBe(6);
  });
});

describe("formatZoom", () => {
  it("trims trailing zeros but keeps fractional precision", () => {
    expect(formatZoom(1)).toBe("1");
    expect(formatZoom(0.5)).toBe("0.5");
    expect(formatZoom(1.5)).toBe("1.5");
    expect(formatZoom(10)).toBe("10");
  });

  it("keeps continuous (non-step) zooms readable", () => {
    expect(formatZoom(2.333)).toBe("2.333");
    expect(formatZoom(2.71828)).toBe("2.718");
  });
});

describe("zoom button stepping", () => {
  it("continues beyond the preset steps without an upper zoom limit", () => {
    expect(nextZoomStepUp(10, STEPS, Infinity)).toBe(20);
    expect(nextZoomStepUp(20, STEPS, Infinity)).toBe(40);
    expect(nextZoomStepDown(40, STEPS, 0.5)).toBe(20);
    expect(nextZoomStepDown(11, STEPS, 0.5)).toBe(10);
  });
  it("climbs to the next step above the current (continuous) zoom", () => {
    expect(nextZoomStepUp(1, STEPS, 10)).toBe(1.5);
    expect(nextZoomStepUp(2.4, STEPS, 10)).toBe(3);
    expect(nextZoomStepUp(10, STEPS, 10)).toBe(10); // already at max
  });

  it("drops to the previous step below the current zoom", () => {
    expect(nextZoomStepDown(1, STEPS, 0.5)).toBe(0.5);
    expect(nextZoomStepDown(2.4, STEPS, 0.5)).toBe(2);
    expect(nextZoomStepDown(10, STEPS, 0.5)).toBe(8);
    expect(nextZoomStepDown(0.4, STEPS, 0.5)).toBe(0.5); // min floor
  });
});

// Event handlers only need these frame methods, not a browser DOM.
const frame = {
  clientWidth: 760,
  clientHeight: 260,
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 760, height: 260 }),
  setPointerCapture: () => {},
  releasePointerCapture: () => {},
} as unknown as HTMLDivElement;

function wheel(g: CoilPreviewGestures, x: number, y: number, deltaY: number) {
  g.handleWheel({
    currentTarget: frame, ctrlKey: true, clientX: x, clientY: y,
    deltaY, preventDefault: () => {},
  } as unknown as WheelEvent);
}

function worldAt(g: CoilPreviewGestures, x: number, y: number) {
  const t = g.getWorldTransform(g.zoom);
  return { x: (x - t.tx - g.panX) / t.s, y: (t.ty + g.panY - y) / t.s };
}

describe("preview edge zoom anchoring", () => {
  const centeredTransform = (zoom: number) => ({ s: zoom, tx: 380 - 380 * zoom, ty: 130 });

  it.each([24, 736])("keeps the trace end under the wheel cursor at x=%s", (x) => {
    const g = makeGestures({ maxZoom: Infinity, getWorldTransform: centeredTransform });
    const original = worldAt(g, x, 24);
    for (let i = 0; i < 8; i += 1) {
      wheel(g, x, 24, -100);
      expect(worldAt(g, x, 24).x).toBeCloseTo(original.x, 8);
      expect(worldAt(g, x, 24).y).toBeCloseTo(original.y, 8);
    }
    expect(g.zoom).toBe(256);
    expect(Math.abs(g.panX)).toBeGreaterThan(760);
    expect(Math.abs(g.panY)).toBeGreaterThan(260);
    for (let i = 0; i < 8; i += 1) wheel(g, x, 24, 100);
    expect(g.zoom).toBe(1);
    expect(g.panX).toBeCloseTo(0, 8);
    expect(g.panY).toBeCloseTo(0, 8);
  });

  it.each([24, 736])("keeps the trace end anchored through a touch pinch at x=%s", (x) => {
    const g = makeGestures({ maxZoom: Infinity, getWorldTransform: centeredTransform });
    const original = worldAt(g, x, 24);
    const touchEvent = (distance: number) => ({
      currentTarget: frame,
      touches: [
        { identifier: 1, clientX: x - distance / 2, clientY: 24 },
        { identifier: 2, clientX: x + distance / 2, clientY: 24 },
      ],
      preventDefault: () => {},
    } as unknown as TouchEvent);
    g.handleTouchStart(touchEvent(2));
    g.handleTouchMove(touchEvent(128));
    expect(g.zoom).toBe(64);
    expect(worldAt(g, x, 24).x).toBeCloseTo(original.x, 8);
    expect(worldAt(g, x, 24).y).toBeCloseTo(original.y, 8);
  });

  it("pans beyond a viewport and keeps the inspected center with zoom buttons", () => {
    const g = makeGestures({ maxZoom: Infinity, getWorldTransform: centeredTransform });
    const pointer = (x: number, y: number) => ({
      currentTarget: frame, pointerId: 1, pointerType: "mouse", button: 0,
      clientX: x, clientY: y, preventDefault: () => {},
    } as unknown as PointerEvent);
    g.handlePointerDown(pointer(380, 130));
    g.handlePointerMove(pointer(2380, 1130));
    g.handlePointerEnd(pointer(2380, 1130));
    expect(g.panX).toBe(2000);
    expect(g.panY).toBe(1000);
    const original = worldAt(g, 380, 130);
    for (let i = 0; i < 15; i += 1) g.zoomIn();
    expect(g.zoom).toBeGreaterThan(10);
    expect(worldAt(g, 380, 130)).toEqual(original);
    g.zoomOut();
    expect(worldAt(g, 380, 130)).toEqual(original);
    g.zoomReset();
    expect(worldAt(g, 380, 130)).toEqual(original);
    g.resetView();
    expect(g.panX).toBe(0);
    expect(g.panY).toBe(0);
  });
});

describe("CoilPreviewGestures (instance-level, no DOM needed)", () => {
  it("reads resized viewport dimensions when anchoring zoom", () => {
    let width = 760;
    let height = 260;
    const g = new CoilPreviewGestures({
      get virtualW() { return width; },
      get virtualH() { return height; },
      minZoom: 0.5,
      maxZoom: Infinity,
      zoomSteps: STEPS,
      getWorldTransform: (zoom) => ({ s: zoom, tx: 0, ty: 0 }),
    });
    width = 1000;
    height = 600;
    const center = worldAt(g, width / 2, height / 2);
    g.zoomIn();
    expect(g.virtualW).toBe(width);
    expect(g.virtualH).toBe(height);
    expect(worldAt(g, width / 2, height / 2)).toEqual(center);
  });

  it("starts at 1×", () => {
    const g = makeGestures();
    expect(g.zoom).toBe(1);
    expect(g.zoomLabel).toBe("1");
    expect(g.canZoomIn).toBe(false);
    expect(g.canZoomOut).toBe(false);
  });

  it("steps zoom with buttons and disables at the bounds", () => {
    const g = makeGestures();
    g.zoomIn();
    expect(g.zoom).toBe(1.5);
    g.zoomReset();
    expect(g.zoom).toBe(1);
    for (let i = 0; i < 12; i += 1) g.zoomIn();
    expect(g.zoom).toBe(10);
    expect(g.canZoomIn).toBe(true);
    expect(g.canZoomOut).toBe(false);
    for (let i = 0; i < 12; i += 1) g.zoomOut();
    expect(g.zoom).toBe(0.5);
    expect(g.canZoomOut).toBe(true);
  });

  it("resetView clears zoom and pan but keeps bounds", () => {
    const g = makeGestures();
    g.zoom = 7;
    g.panX = 60;
    g.panY = -40;
    g.resetView();
    expect(g.zoom).toBe(1);
    expect(g.panX).toBe(0);
    expect(g.panY).toBe(0);
  });

  it("continuous pinch math stays clamped via the exposed zoom assignment", () => {
    // Direct zoom writes are allowed on the class instance; the clamp is the
    // gesture path's responsibility (handled by updatePinch → clampZoom).
    const g = makeGestures();
    g.zoom = clampZoom(g.zoom * 3, g.minZoom, g.maxZoom);
    expect(g.zoom).toBe(3);
    g.zoom = clampZoom(g.zoom * 4, g.minZoom, g.maxZoom);
    expect(g.zoom).toBe(10); // clamped to max
  });
});

describe("CAD navigation", () => {
  function touch(points: { x: number; y: number }[]) {
    return { currentTarget: frame, touches: points.map((p, i) => ({ identifier: i, clientX: p.x, clientY: p.y })), preventDefault: () => {} } as unknown as TouchEvent;
  }
  it("reserves one finger for selection and pans with two without changing zoom", () => {
    const g = makeGestures({ interactionMode: "cad" });
    g.handleTouchStart(touch([{ x: 100, y: 100 }]));
    g.handleTouchMove(touch([{ x: 150, y: 130 }]));
    expect(g.panX).toBe(0);
    expect(g.isPanning).toBe(false);
    g.handleTouchStart(touch([{ x: 100, y: 100 }, { x: 200, y: 100 }]));
    g.handleTouchMove(touch([{ x: 80, y: 100 }, { x: 220, y: 100 }]));
    expect(g.zoom).toBe(1);
    expect(g.panX).toBe(0);
    g.handleTouchMove(touch([{ x: 90, y: 120 }, { x: 230, y: 120 }]));
    expect(g.panX).toBe(10);
    expect(g.panY).toBe(20);
  });
  it("anchors three-finger pinch and rebases cleanly through 3 to 2 to 1 fingers", () => {
    const g = makeGestures({ interactionMode: "cad" });
    const points = [{ x: 100, y: 100 }, { x: 200, y: 100 }, { x: 150, y: 190 }];
    g.handleTouchStart(touch(points));
    const original = worldAt(g, 150, 130);
    const expanded = points.map(p => ({ x: 150 + (p.x - 150) * 2 + 15, y: 130 + (p.y - 130) * 2 - 10 }));
    g.handleTouchMove(touch(expanded));
    expect(g.zoom).toBeCloseTo(2);
    expect(worldAt(g, 165, 120).x).toBeCloseTo(original.x);
    expect(worldAt(g, 165, 120).y).toBeCloseTo(original.y);
    const pan = { x: g.panX, y: g.panY };
    g.handleTouchEnd(touch(expanded.slice(0, 2)));
    g.handleTouchMove(touch(expanded.slice(0, 2)));
    expect({ x: g.panX, y: g.panY }).toEqual(pan);
    g.handleTouchMove(touch(expanded.slice(0, 2).map(p => ({ x: p.x + 10, y: p.y }))));
    expect(g.panX).toBeCloseTo(pan.x + 10);
    expect(g.zoom).toBeCloseTo(2);
    g.handleTouchEnd(touch(expanded.slice(0, 1)));
    const endPan = g.panX;
    g.handleTouchMove(touch([{ x: 400, y: 100 }]));
    expect(g.panX).toBe(endPan);
    expect(g.isPanning).toBe(false);
    g.handleTouchEnd(touch([]));
  });
  it("supports two-pan and three-pinch on pointer-only touch devices", () => {
    const g = makeGestures({ interactionMode: "cad" });
    const pointer = (id: number, x: number, y: number) => ({ currentTarget: frame, pointerId: id, pointerType: "touch", button: 0, clientX: x, clientY: y, preventDefault: () => {} }) as unknown as PointerEvent;
    g.handlePointerDown(pointer(1, 100, 100));
    g.handlePointerDown(pointer(2, 200, 100));
    g.handlePointerMove(pointer(1, 80, 100));
    g.handlePointerMove(pointer(2, 220, 100));
    expect(g.zoom).toBe(1);
    g.handlePointerDown(pointer(3, 150, 190));
    g.handlePointerMove(pointer(1, 10, 70));
    g.handlePointerMove(pointer(2, 290, 70));
    g.handlePointerMove(pointer(3, 150, 250));
    expect(g.zoom).toBeCloseTo(2);
    g.handlePointerEnd(pointer(3, 150, 250));
    const before = g.panX;
    g.handlePointerMove(pointer(1, 10, 70));
    expect(g.panX).toBe(before);
  });
  it("pans with middle mouse and trackpad scroll, while Ctrl-scroll zooms", () => {
    const g = makeGestures({ interactionMode: "cad" });
    const pointer = (button: number, x: number) => ({ currentTarget: frame, pointerId: 1, pointerType: "mouse", button, clientX: x, clientY: 100, preventDefault: () => {} }) as unknown as PointerEvent;
    g.handlePointerDown(pointer(0, 100));
    g.handlePointerMove(pointer(0, 200));
    expect(g.panX).toBe(0);
    g.handlePointerDown(pointer(1, 100));
    g.handlePointerMove(pointer(1, 200));
    g.handlePointerEnd(pointer(1, 200));
    expect(g.panX).toBe(100);
    g.handleWheel({ currentTarget: frame, ctrlKey: false, deltaX: 10, deltaY: 20, deltaMode: 0, preventDefault: () => {} } as unknown as WheelEvent);
    expect(g.panX).toBe(90);
    expect(g.panY).toBe(-20);
    expect(g.zoom).toBe(1);
    wheel(g, 300, 100, -100);
    expect(g.zoom).toBe(2);
  });
});
