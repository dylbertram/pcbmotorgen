/**
 * Two-click ruler state for motor and CAD canvas previews.
 *
 * Click 1 sets the start point, click 2 locks
 * the dimension, click 3 clears it. The toolbar's Reset button clears
 * without a click, and toggling the mode off clears too. Taps are
 * distinguished from pan-drags by a movement threshold (MEASURE_TAP_PX), so
 * pan/pinch/zoom keep working while measuring.
 *
 * Input routes (mirroring the gesture utility's dual routing):
 *   - PointerEvents: mouse (primary button) and pen. On browsers that also
 *     deliver native TouchEvents (`ontouchstart in window`), touch-compat
 *     PointerEvents are ignored ENTIRELY — the native touch route owns tap
 *     detection there, exactly like gesture ownership.
 *   - Native TouchEvents (touchstart/touchend): tap positions are tracked in
 *     a per-identifier map, and a touch only counts as a tap when NO other
 *     finger remains down (so two-finger pinches never place points).
 *
 * The caller supplies screen-to-world conversion under the current camera;
 * the locked dimension's bounds can then participate in camera fit.
 */

import { computeMeasureRuler, type Point2D } from "./measureRuler";

/** Max pointer travel (px) between down and up that still counts as a tap. */
export const MEASURE_TAP_PX = 6;

export interface PreviewMeasureOptions {
  /**
   * Client-viewport position → world metres under the CURRENT camera.
   * Returns null when the measure surface is not mounted.
   */
  screenToWorld: (clientX: number, clientY: number) => Point2D | null;
}

interface Point {
  x: number;
  y: number;
}

export class PreviewMeasure {
  // --- reactive view state ---------------------------------------------------
  /** Ruler mode on/off (the Measure toolbar toggle). */
  mode = $state(false);
  /** Click 1: locked start point (world m). */
  p1 = $state<Point2D | null>(null);
  /** Click 2: locked end point (world m). */
  p2 = $state<Point2D | null>(null);
  /** Live end point while hovering between the two clicks (world m). */
  cursor = $state<Point2D | null>(null);
  /** Camera-fit bounds of the LOCKED dimension (overlayFitBounds input). */
  lockedBounds = $derived(
    this.p1 && this.p2 ? computeMeasureRuler(this.p1, this.p2).bounds : null,
  );

  // --- tap bookkeeping (deliberately NON-reactive, like the gesture maps) ---
  #screenToWorld: PreviewMeasureOptions["screenToWorld"];
  #touchCapable: boolean;
  #downs = new Map<number, Point>();
  #touches = new Map<number, Point>();
  #multiPointer = false;
  #multiTouch = false;

  constructor(options: PreviewMeasureOptions) {
    this.#screenToWorld = options.screenToWorld;
    // Native touch events, when present, own ALL touch tap detection.
    this.#touchCapable =
      typeof window !== "undefined" && "ontouchstart" in window;
  }

  // --- toolbar controls ------------------------------------------------------
  toggleMode = () => {
    this.mode = !this.mode;
    if (!this.mode) this.clear();
  };
  clear = () => {
    this.p1 = null;
    this.p2 = null;
    this.cursor = null;
  };

  // --- tap state machine -----------------------------------------------------
  /** Three-state click cycle: set start → lock dimension → clear. */
  #tapAt(clientX: number, clientY: number): void {
    if (!this.mode) return;
    const w = this.#screenToWorld(clientX, clientY);
    if (!w) return;
    if (!this.p1) {
      this.p1 = w;
      this.cursor = null;
    } else if (!this.p2) {
      this.p2 = w;
      this.cursor = null;
    } else {
      // Third click clears the locked measurement.
      this.p1 = null;
      this.p2 = null;
      this.cursor = null;
    }
  }

  // --- pointer route (mouse / pen; touch only where native touch is absent) --
  handlePointerDown = (e: PointerEvent) => {
    // Only the primary mouse button (or a pen pointer) starts a tap.
    if (e.pointerType === "mouse" && e.button !== 0) return;
    // Browsers with native TouchEvents own ALL touch there — the touch route
    // below handles taps; ignore the touch-compat pointer entirely.
    if (e.pointerType === "touch" && this.#touchCapable) return;
    this.#downs.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (this.#downs.size > 1) this.#multiPointer = true;
  };

  /** Live preview: while placing the end point, track the pointer (mouse/
   *  pen only — the touch route updates the cursor in handleTouchMove). */
  handlePointerMove = (e: PointerEvent) => {
    if (this.mode && this.p1 && !this.p2 && e.pointerType !== "touch") {
      const w = this.#screenToWorld(e.clientX, e.clientY);
      if (w) this.cursor = w;
    }
  };

  handlePointerUp = (e: PointerEvent) => {
    if (e.pointerType === "touch" && this.#touchCapable) return;
    const down = this.#downs.get(e.pointerId);
    this.#downs.delete(e.pointerId);
    if (this.#multiPointer) { if (this.#downs.size === 0) this.#multiPointer = false; return; }
    if (!down) return;
    if (this.#downs.size > 0) return; // a second pointer was part of a pinch
    if (Math.hypot(e.clientX - down.x, e.clientY - down.y) <= MEASURE_TAP_PX) {
      this.#tapAt(e.clientX, e.clientY);
    }
  };

  handlePointerCancel = (e: PointerEvent) => {
    this.#downs.delete(e.pointerId);
    if (this.#downs.size === 0) this.#multiPointer = false;
  };

  // --- native touch route ------------------------------------------------------
  handleTouchStart = (e: TouchEvent) => {
    if (e.touches.length > 1) this.#multiTouch = true;
    for (const t of e.changedTouches) {
      this.#touches.set(t.identifier, { x: t.clientX, y: t.clientY });
    }
    if (this.#touches.size > 1) this.#multiTouch = true;
  };

  /** Live preview for touch: track the first finger while placing. */
  handleTouchMove = (e: TouchEvent) => {
    if (this.mode && this.p1 && !this.p2) {
      const t = e.touches[0];
      if (t) {
        const w = this.#screenToWorld(t.clientX, t.clientY);
        if (w) this.cursor = w;
      }
    }
  };

  handleTouchEnd = (e: TouchEvent) => {
    const multiTouch = this.#multiTouch;
    for (const t of e.changedTouches) {
      const down = this.#touches.get(t.identifier);
      this.#touches.delete(t.identifier);
      if (multiTouch) continue;
      if (!down) continue;
      if (e.touches.length > 0) continue; // other fingers still down (pinch)
      if (Math.hypot(t.clientX - down.x, t.clientY - down.y) <= MEASURE_TAP_PX) {
        this.#tapAt(t.clientX, t.clientY);
      }
    }
    if (e.touches.length === 0) this.#multiTouch = false;
  };

  handleTouchCancel = (e: TouchEvent) => {
    for (const t of e.changedTouches) this.#touches.delete(t.identifier);
    if (e.touches.length === 0) this.#multiTouch = false;
  };
}
