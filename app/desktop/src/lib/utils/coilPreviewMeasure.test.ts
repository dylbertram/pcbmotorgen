import { describe, it, expect } from "vitest";
import { CoilPreviewMeasure, MEASURE_TAP_PX } from "./coilPreviewMeasure.svelte";
import type { Point2D } from "../previewGeometry";

/**
 * Deterministic fake camera: 1 client px → (x/100, y/100) world metres.
 * Returns null while `frameGone` so the "surface not mounted" path is
 * testable without a DOM.
 */
function makeCamera(frameGone = false) {
  return (clientX: number, clientY: number): Point2D | null =>
    frameGone ? null : { x: clientX / 100, y: clientY / 100 };
}

function makeMeasure(frameGone = false): CoilPreviewMeasure {
  return new CoilPreviewMeasure({ screenToWorld: makeCamera(frameGone) });
}

/** Minimal PointerEvent stand-in (the module only reads a few fields). */
function pointerEvent(overrides: Partial<PointerEvent> = {}): PointerEvent {
  return {
    pointerId: 1,
    pointerType: "mouse",
    button: 0,
    clientX: 100,
    clientY: 100,
    ...overrides,
  } as PointerEvent;
}

/** Minimal TouchEvent stand-in over plain Touch objects. */
function touchEvent(
  changedTouches: { identifier: number; clientX: number; clientY: number }[],
  touches: { identifier: number; clientX: number; clientY: number }[] = [],
): TouchEvent {
  return { changedTouches, touches } as unknown as TouchEvent;
}

/** Down + up at the same client position (a clean tap). */
function tap(m: CoilPreviewMeasure, e: PointerEvent) {
  m.handlePointerDown(e);
  m.handlePointerUp(e);
}

describe("CoilPreviewMeasure (instance-level, no DOM needed)", () => {
  it("starts inactive with no points", () => {
    const m = makeMeasure();
    expect(m.mode).toBe(false);
    expect(m.p1).toBeNull();
    expect(m.p2).toBeNull();
    expect(m.cursor).toBeNull();
    expect(m.lockedBounds).toBeNull();
  });

  it("ignores taps while the mode is off", () => {
    const m = makeMeasure();
    tap(m, pointerEvent());
    expect(m.p1).toBeNull();
  });

  it("toggleMode flips the mode and turning it off clears the points", () => {
    const m = makeMeasure();
    m.toggleMode();
    expect(m.mode).toBe(true);
    tap(m, pointerEvent());
    expect(m.p1).not.toBeNull();
    m.toggleMode();
    expect(m.mode).toBe(false);
    expect(m.p1).toBeNull();
    expect(m.p2).toBeNull();
    expect(m.cursor).toBeNull();
  });

  it("click 1 sets the start, click 2 locks the dimension, click 3 clears", () => {
    const m = makeMeasure();
    m.toggleMode();
    tap(m, pointerEvent({ clientX: 100, clientY: 100 }));
    expect(m.p1).toEqual({ x: 1, y: 1 });
    expect(m.p2).toBeNull();

    tap(m, pointerEvent({ clientX: 300, clientY: 200 }));
    expect(m.p2).toEqual({ x: 3, y: 2 });
    // The locked dimension carries camera-fit bounds.
    expect(m.lockedBounds).not.toBeNull();
    expect(m.lockedBounds!.minX).toBeLessThan(m.p1!.x);

    tap(m, pointerEvent({ clientX: 150, clientY: 150 }));
    expect(m.p1).toBeNull();
    expect(m.p2).toBeNull();
    expect(m.lockedBounds).toBeNull();
  });

  it("pointer travel beyond the tap threshold is a drag, not a tap", () => {
    const m = makeMeasure();
    m.toggleMode();
    m.handlePointerDown(pointerEvent({ clientX: 100, clientY: 100 }));
    m.handlePointerUp(
      pointerEvent({ clientX: 100 + MEASURE_TAP_PX + 1, clientY: 100 }),
    );
    expect(m.p1).toBeNull();

    // Exactly at the threshold still counts as a tap.
    m.handlePointerDown(pointerEvent({ clientX: 100, clientY: 100 }));
    m.handlePointerUp(
      pointerEvent({ clientX: 100 + MEASURE_TAP_PX, clientY: 100 }),
    );
    expect(m.p1).not.toBeNull();
  });

  it("non-primary mouse buttons never tap", () => {
    const m = makeMeasure();
    m.toggleMode();
    tap(m, pointerEvent({ button: 2 }));
    expect(m.p1).toBeNull();
  });

  it("a second concurrent pointer suppresses the tap (pinch guard)", () => {
    const m = makeMeasure();
    m.toggleMode();
    m.handlePointerDown(pointerEvent({ pointerId: 1 }));
    m.handlePointerDown(pointerEvent({ pointerId: 2 }));
    // Releasing one finger of the pinch must NOT place a point…
    m.handlePointerUp(pointerEvent({ pointerId: 1 }));
    expect(m.p1).toBeNull();
    // …and the remaining pointer's release was a drag anyway.
    m.handlePointerUp(pointerEvent({ pointerId: 2, clientX: 400, clientY: 100 }));
    expect(m.p1).toBeNull();
  });

  it("a cancelled pointer leaves no stale bookkeeping behind", () => {
    const m = makeMeasure();
    m.toggleMode();
    m.handlePointerDown(pointerEvent({ pointerId: 1 }));
    m.handlePointerCancel(pointerEvent({ pointerId: 1 }));
    // The next tap is a lone tap again (the cancelled pointer is forgotten).
    tap(m, pointerEvent({ pointerId: 2 }));
    expect(m.p1).not.toBeNull();
  });

  it("never places a point when the measure surface is not mounted", () => {
    const m = makeMeasure(true);
    m.toggleMode();
    tap(m, pointerEvent());
    expect(m.p1).toBeNull();
    expect(m.p2).toBeNull();
  });

  it("tracks a live cursor between click 1 and click 2 (mouse/pen only)", () => {
    const m = makeMeasure();
    m.toggleMode();
    tap(m, pointerEvent({ clientX: 100, clientY: 100 }));
    m.handlePointerMove(pointerEvent({ clientX: 150, clientY: 120 }));
    expect(m.cursor).toEqual({ x: 1.5, y: 1.2 });

    // After the dimension is locked the live cursor stops updating.
    tap(m, pointerEvent({ clientX: 300, clientY: 200 }));
    m.handlePointerMove(pointerEvent({ clientX: 400, clientY: 400 }));
    expect(m.cursor).toBeNull();
  });

  it("touch taps land through the native touch route", () => {
    const m = makeMeasure();
    m.toggleMode();
    // Click 1 through the touch route…
    m.handleTouchStart(
      touchEvent([{ identifier: 5, clientX: 200, clientY: 100 }]),
    );
    m.handleTouchEnd(
      touchEvent([{ identifier: 5, clientX: 200, clientY: 100 }], []),
    );
    expect(m.p1).toEqual({ x: 2, y: 1 });

    // …then the moving finger feeds the live cursor while placing the end.
    m.handleTouchStart(
      touchEvent([{ identifier: 6, clientX: 200, clientY: 100 }]),
    );
    m.handleTouchMove(
      touchEvent([], [{ identifier: 6, clientX: 210, clientY: 100 }]),
    );
    expect(m.cursor).toEqual({ x: 2.1, y: 1 });

    // Click 2 locks the dimension and resets the live cursor (the tap end
    // sits within the threshold of the recorded touchstart position).
    m.handleTouchEnd(
      touchEvent([{ identifier: 6, clientX: 202, clientY: 100 }], []),
    );
    expect(m.p2).toEqual({ x: 2.02, y: 1 });
    expect(m.cursor).toBeNull();
  });

  it("a lifted pinch finger never taps (other fingers still down)", () => {
    const m = makeMeasure();
    m.toggleMode();
    m.handleTouchStart(
      touchEvent([
        { identifier: 1, clientX: 200, clientY: 100 },
        { identifier: 2, clientX: 260, clientY: 100 },
      ]),
    );
    m.handleTouchEnd(
      touchEvent([{ identifier: 1, clientX: 200, clientY: 100 }], [
        { identifier: 2, clientX: 260, clientY: 100 },
      ]),
    );
    expect(m.p1).toBeNull();
    m.handleTouchEnd(touchEvent([{ identifier: 2, clientX: 260, clientY: 100 }], []));
    expect(m.p1).toBeNull();
  });

  it("a cancelled touch leaves no stale bookkeeping behind", () => {
    const m = makeMeasure();
    m.toggleMode();
    m.handleTouchStart(
      touchEvent([{ identifier: 1, clientX: 200, clientY: 100 }]),
    );
    m.handleTouchCancel(
      touchEvent([{ identifier: 1, clientX: 200, clientY: 100 }]),
    );
    m.handleTouchEnd(
      touchEvent([{ identifier: 1, clientX: 200, clientY: 100 }], []),
    );
    expect(m.p1).toBeNull();
  });

  it("clear() resets the tool without touching the mode", () => {
    const m = makeMeasure();
    m.toggleMode();
    tap(m, pointerEvent({ clientX: 100, clientY: 100 }));
    tap(m, pointerEvent({ clientX: 300, clientY: 200 }));
    m.clear();
    expect(m.mode).toBe(true);
    expect(m.p1).toBeNull();
    expect(m.p2).toBeNull();
    expect(m.cursor).toBeNull();
    expect(m.lockedBounds).toBeNull();
  });
});
