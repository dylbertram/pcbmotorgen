/**
 * coilPreviewGestures.svelte.ts
 * ============================================================================
 * Pan / pinch / scroll-zoom state machine for the canvas coil preview.
 *
 * EVERY gesture concern lives here — reactive `$state` view fields + arrow-
 * function DOM handlers — so CoilPreview.svelte only instantiates this class,
 * forwards events, and reads the reactive values. The class has NO preview
 * geometry knowledge: the component injects `getWorldTransform(zoom)` (backed
 * by `lib/chart`'s fitWorldToView), the virtual canvas dimensions and the zoom
 * bounds/steps.
 *
 * Input routes:
 *   - PointerEvents: mouse (primary button) and pen. On browsers that also
 *     deliver native TouchEvents (`ontouchstart in window`), touch-compat
 *     PointerEvents are ignored ENTIRELY. This is the key robustness fix:
 *     WebKit/Chrome commonly fire `pointerdown` BEFORE `touchstart`, and
 *     because the touch-compat pointer never claims the gesture channel, the
 *     native touch stream can always take ownership and two-finger pinches
 *     are never starved.
 *   - Native TouchEvents (touchstart/touchmove/touchend/cancel): the reliable
 *     two-finger path on mobile WebKit/WKWebView. The finger map is ALWAYS
 *     rebuilt from the full live `e.touches` TouchList, so fingers are never
 *     lost (including the first finger while a second lands and the one that
 *     remains for a pinch→pan handoff).
 *   - ctrl+Wheel (macOS trackpad pinch / browser pinch-zoom): focal-point
 *     zoom about the cursor with `preventDefault()` so the page never zooms.
 *     The component must attach the handler NON-passively.
 *
 * Zoom is CONTINUOUS and clamped to [minZoom, maxZoom]; the zoom BUTTONS step
 * through `zoomSteps`. All focal-point anchoring reuses the injected
 * `getWorldTransform` so this module never duplicates preview geometry.
 */

import type { WorldTransform } from "../chart";

// ---------------------------------------------------------------------------
// Pure zoom helpers (unit-tested; no DOM or Svelte state involved)
// ---------------------------------------------------------------------------

/** Clamp a zoom level into [min, max]. */
export function clampZoom(value: number, min = 0.5, max = Infinity): number {
  return Math.min(max, Math.max(min, value));
}

/** Render a zoom level for the button label, trimming trailing zeros. */
export function formatZoom(value: number): string {
  return String(Math.round(value * 1000) / 1000);
}

/** Use preset steps, then double the zoom until an optional maximum. */
export function nextZoomStepUp(
  zoom: number,
  steps: readonly number[],
  max: number,
): number {
  const found = steps.find((step) => step > zoom + 1e-6);
  return Math.min(found ?? zoom * 2, max);
}

/** Largest zoom step strictly below `zoom`, or `min` when already at the bottom. */
export function nextZoomStepDown(
  zoom: number,
  steps: readonly number[],
  min: number,
): number {
  const lastStep = steps[steps.length - 1];
  if (lastStep !== undefined && zoom > lastStep + 1e-6) {
    return Math.max(lastStep, zoom / 2, min);
  }
  const found = [...steps].reverse().find((step) => step < zoom - 1e-6);
  return Math.max(found ?? min, min);
}

// ---------------------------------------------------------------------------
// Options / type aliases
// ---------------------------------------------------------------------------

export interface CoilPreviewGesturesOptions {
  /** Virtual drawing-space width (the canvas maps to 760 virtual px). */
  virtualW: number;
  /** Virtual drawing-space height. */
  virtualH: number;
  minZoom: number;
  maxZoom: number;
  /** Discrete zoom levels used by the zoom buttons. */
  zoomSteps: readonly number[];
  /** World→virtual transform for a given zoom level (component geometry). */
  getWorldTransform: (zoom: number) => WorldTransform;
}

interface Point {
  x: number;
  y: number;
}
interface PointerEntry extends Point {
  pointerType: string;
}

// ---------------------------------------------------------------------------
// Gesture class
// ---------------------------------------------------------------------------

export class CoilPreviewGestures {
  // --- options -------------------------------------------------------------
  readonly virtualW: number;
  readonly virtualH: number;
  readonly minZoom: number;
  readonly maxZoom: number;
  readonly zoomSteps: readonly number[];
  readonly getWorldTransform: (zoom: number) => WorldTransform;

  // --- reactive view state (binds straight into CoilPreview's template) ----
  zoom = $state(1);
  panX = $state(0);
  panY = $state(0);
  isPanning = $state(false);
  zoomLabel = $derived(formatZoom(this.zoom));
  canZoomIn = $derived(this.zoom >= this.maxZoom - 1e-6);
  canZoomOut = $derived(this.zoom <= this.minZoom + 1e-6);

  // --- gesture bookkeeping (deliberately NON-reactive) ----------------------
  #touchCapable: boolean;
  #channel: "none" | "touch" | "pointer" = "none";
  #touchPoints = new Map<number, Point>();
  #pointerPoints = new Map<number, PointerEntry>();
  #panFrame: HTMLDivElement | null = null;
  #panStartClientX = 0;
  #panStartClientY = 0;
  #panStartPanX = 0;
  #panStartPanY = 0;
  #pinchStart = { distance: 0, cx: 0, cy: 0, zoom: 1, panX: 0, panY: 0 };

  constructor(options: CoilPreviewGesturesOptions) {
    this.virtualW = options.virtualW;
    this.virtualH = options.virtualH;
    this.minZoom = options.minZoom;
    this.maxZoom = options.maxZoom;
    this.zoomSteps = options.zoomSteps;
    this.getWorldTransform = options.getWorldTransform;
    this.zoom = clampZoom(1, this.minZoom, this.maxZoom);
    // Native touch events, when present, own ALL touch gestures.
    this.#touchCapable =
      typeof window !== "undefined" && "ontouchstart" in window;
  }

  // --- public controls ------------------------------------------------------
  zoomIn = () => {
    this.#zoomAtCenter(nextZoomStepUp(this.zoom, this.zoomSteps, this.maxZoom));
  };
  zoomOut = () => {
    this.#zoomAtCenter(nextZoomStepDown(this.zoom, this.zoomSteps, this.minZoom));
  };
  zoomReset = () => {
    this.#zoomAtCenter(clampZoom(1, this.minZoom, this.maxZoom));
  };
  resetView = () => {
    this.zoom = clampZoom(1, this.minZoom, this.maxZoom);
    this.panX = 0;
    this.panY = 0;
  };

  // --- coordinate helpers -----------------------------------------------------
  #zoomAtCenter(target: number): void {
    if (!Number.isFinite(target) || target === this.zoom) return;
    this.#anchorWorld(
      this.virtualW / 2, this.virtualH / 2,
      this.zoom, this.panX, this.panY,
      this.virtualW / 2, this.virtualH / 2, target,
    );
    this.zoom = target;
  }
  #clientToVirtual(
    frame: HTMLDivElement,
    clientX: number,
    clientY: number,
  ): Point {
    const rect = frame.getBoundingClientRect();
    return {
      x: rect.width > 0 ? ((clientX - rect.left) / rect.width) * this.virtualW : 0,
      y: rect.height > 0 ? ((clientY - rect.top) / rect.height) * this.virtualH : 0,
    };
  }

  // --- shared pan / pinch primitives (pointer AND touch route into these) ----
  /**
   * Keep the world point that sat at (startVx, startVy) under `startPan`
   * while the transform went from `startZoom` to `endZoom`, pinned under
   * (endVx, endVy) in virtual px. Used by pinch (start centroid → current
   * centroid) AND by ctrl+wheel (cursor stays the anchor).
   */
  #anchorWorld(
    startVx: number,
    startVy: number,
    startZoom: number,
    startPanX: number,
    startPanY: number,
    endVx: number,
    endVy: number,
    endZoom: number,
  ): void {
    const oldT = this.getWorldTransform(startZoom);
    const newT = this.getWorldTransform(endZoom);
    if (oldT.s <= 0 || newT.s <= 0) return;
    // screen = (tx + panX + s*wx, ty + panY − s*wy)
    const wx = (startVx - oldT.tx - startPanX) / oldT.s;
    const wy = (oldT.ty + startPanY - startVy) / oldT.s;
    // Focal zoom at a trace end can require offsets many viewports wide.
    // Clamping these offsets breaks the anchor and drags the view inward.
    this.panX = endVx - newT.tx - newT.s * wx;
    this.panY = endVy - newT.ty + newT.s * wy;
  }

  #beginPan(frame: HTMLDivElement | null | undefined, x: number, y: number): void {
    if (!frame) return;
    this.isPanning = true;
    this.#panStartClientX = x;
    this.#panStartClientY = y;
    this.#panStartPanX = this.panX;
    this.#panStartPanY = this.panY;
  }

  /** Resume one-finger panning anchored on the remaining finger/pointer. */
  #resumePan(frame: HTMLDivElement | null | undefined, x: number, y: number): void {
    this.#beginPan(frame, x, y);
  }

  #beginPinch(frame: HTMLDivElement, a: Point, b: Point): void {
    this.isPanning = false;
    const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    const v = this.#clientToVirtual(frame, mid.x, mid.y);
    this.#pinchStart = {
      distance: Math.hypot(b.x - a.x, b.y - a.y),
      zoom: this.zoom,
      panX: this.panX,
      panY: this.panY,
      cx: v.x,
      cy: v.y,
    };
  }

  #updatePan(frame: HTMLDivElement, x: number, y: number): void {
    if (!frame || !this.isPanning) return;
    if (frame.clientWidth === 0 || frame.clientHeight === 0) return;
    // Same ratio math as the old SVG viewBox → rendered-size scale.
    const sx = this.virtualW / frame.clientWidth;
    const sy = this.virtualH / frame.clientHeight;
    const dx = (x - this.#panStartClientX) * sx;
    const dy = (y - this.#panStartClientY) * sy;
    this.panX = this.#panStartPanX + dx;
    this.panY = this.#panStartPanY + dy;
  }

  #updatePinch(frame: HTMLDivElement, a: Point, b: Point): void {
    if (frame.clientWidth === 0 || frame.clientHeight === 0) return;
    const distance = Math.hypot(b.x - a.x, b.y - a.y);
    if (this.#pinchStart.distance <= 0 || distance <= 0) return;

    // CONTINUOUS zoom clamped to [minZoom, maxZoom] — no step snapping.
    const target = clampZoom(
      this.#pinchStart.zoom * (distance / this.#pinchStart.distance),
      this.minZoom,
      this.maxZoom,
    );
    if (!Number.isFinite(target)) return;
    this.zoom = target;

    // Focal-point anchoring: the world point under the pinch-start centroid
    // stays pinned under the CURRENT centroid while the zoom level changes.
    const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    const v = this.#clientToVirtual(frame, mid.x, mid.y);
    this.#anchorWorld(
      this.#pinchStart.cx,
      this.#pinchStart.cy,
      this.#pinchStart.zoom,
      this.#pinchStart.panX,
      this.#pinchStart.panY,
      v.x,
      v.y,
      target,
    );
  }

  #endGesture(): void {
    this.isPanning = false;
    this.#panFrame = null;
  }

  // --- pointer route (mouse / pen; touch only where native touch is absent) --
  #capturePointer(frame: HTMLDivElement | null | undefined, pointerId: number): void {
    if (!frame) return;
    try {
      frame.setPointerCapture(pointerId);
    } catch {
      // Capture can fail if the pointer is already released — flush later
      // gets called on pointerup/cancel anyway.
    }
  }
  #releasePointerCapture(frame: HTMLDivElement | null | undefined, pointerId: number): void {
    if (!frame) return;
    try {
      frame.releasePointerCapture(pointerId);
    } catch {
      // ignore
    }
  }

  handlePointerDown = (e: PointerEvent) => {
    const frame = e.currentTarget as HTMLDivElement;
    // Only the primary mouse button (or a touch/pen pointer) starts a gesture.
    if (e.pointerType === "mouse" && e.button !== 0) return;
    // Browsers with native TouchEvents own ALL touch there: ignore the
    // touch-compat PointerEvents entirely, so an early `pointerdown` can never
    // claim the channel ahead of `touchstart` and kill the pinch.
    if (e.pointerType === "touch" && this.#touchCapable) return;
    e.preventDefault();
    this.#capturePointer(frame, e.pointerId);

    if (this.#channel === "none") this.#channel = "pointer";
    if (this.#channel !== "pointer") return; // touch owns the gesture
    this.#pointerPoints.set(e.pointerId, {
      x: e.clientX,
      y: e.clientY,
      pointerType: e.pointerType,
    });
    this.#panFrame = frame;

    if (this.#pointerPoints.size === 2) {
      const [a, b] = [...this.#pointerPoints.values()];
      this.#beginPinch(frame, a, b);
      return;
    }
    this.#beginPan(frame, e.clientX, e.clientY);
  };

  handlePointerMove = (e: PointerEvent) => {
    const frame = this.#panFrame;
    if (!frame) return;
    if (e.pointerType === "touch" && this.#touchCapable) return;
    if (!this.#pointerPoints.has(e.pointerId)) return;
    if (this.#channel !== "pointer") return;
    this.#pointerPoints.set(e.pointerId, {
      x: e.clientX,
      y: e.clientY,
      pointerType: e.pointerType,
    });

    if (this.#pointerPoints.size === 2) {
      const [a, b] = [...this.#pointerPoints.values()];
      this.#updatePinch(frame, a, b);
      return;
    }
    this.#updatePan(frame, e.clientX, e.clientY);
  };

  handlePointerEnd = (e: PointerEvent) => {
    if (e.pointerType === "touch" && this.#touchCapable) return;
    this.#pointerPoints.delete(e.pointerId);
    this.#releasePointerCapture(this.#panFrame, e.pointerId);
    if (this.#channel !== "pointer") return; // stale compat teardown

    if (this.#pointerPoints.size === 1) {
      // Pinch → pan handoff: resume on the remaining pointer, no jump.
      const [remaining] = [...this.#pointerPoints.values()];
      this.#resumePan(this.#panFrame, remaining.x, remaining.y);
      return;
    }
    if (this.#pointerPoints.size === 0) {
      this.#channel = "none";
      this.#endGesture();
    }
  };

  /** Safety net: if the browser seizes the pointer capture, drop the gesture. */
  handleLostPointerCapture = (e: PointerEvent) => {
    this.#pointerPoints.delete(e.pointerId);
    if (this.#channel !== "pointer") return;
    if (this.#pointerPoints.size === 0) {
      this.#channel = "none";
      this.#endGesture();
    }
  };

  // --- native touch route (two-finger pinch on mobile WebKit/WKWebView) -----
  /** Rebuild the finger map from the FULL live TouchList so no finger is
   *  ever lost (lifted fingers drop out automatically). */
  #syncTouchPoints(touches: TouchList): void {
    this.#touchPoints.clear();
    for (const touch of touches) {
      this.#touchPoints.set(touch.identifier, {
        x: touch.clientX,
        y: touch.clientY,
      });
    }
  }

  handleTouchStart = (e: TouchEvent) => {
    const frame = e.currentTarget as HTMLDivElement;
    // A mouse/pen drag currently owns the view — never steal it. (Touch-compat
    // pointers never set the channel on touch-capable browsers, so we can only
    // reach this with "none" or "touch".)
    if (this.#channel === "pointer") return;
    if (this.#channel === "none") {
      this.#touchPoints.clear();
      this.#channel = "touch";
    }
    this.#syncTouchPoints(e.touches);
    this.#panFrame = frame;

    if (this.#touchPoints.size === 2) {
      const [a, b] = [...this.#touchPoints.values()];
      this.#beginPinch(frame, a, b);
      return;
    }
    const [a] = [...this.#touchPoints.values()];
    if (a) this.#beginPan(frame, a.x, a.y);
  };

  handleTouchMove = (e: TouchEvent) => {
    const frame = this.#panFrame;
    if (!frame) return;
    if (this.#channel !== "touch") return;
    // The gesture is ours — suppress residual browser pan/zoom.
    e.preventDefault();
    this.#syncTouchPoints(e.touches);

    if (this.#touchPoints.size === 2) {
      const [a, b] = [...this.#touchPoints.values()];
      this.#updatePinch(frame, a, b);
      return;
    }
    const [a] = [...this.#touchPoints.values()];
    if (a) this.#updatePan(frame, a.x, a.y);
  };

  handleTouchEnd = (e: TouchEvent) => {
    if (this.#channel !== "touch") return;
    // The live list excludes the lifted finger(s); the sync below handles the
    // pinch→pan handoff and the final-finger reset.
    this.#syncTouchPoints(e.touches);
    if (this.#touchPoints.size === 1) {
      const [remaining] = [...this.#touchPoints.values()];
      this.#resumePan(this.#panFrame, remaining.x, remaining.y);
      return;
    }
    if (this.#touchPoints.size === 0) {
      this.#channel = "none";
      this.#endGesture();
    }
  };

  // --- ctrl+wheel pinch zoom (macOS trackpad / browser pinch) ----------------
  handleWheel = (e: WheelEvent) => {
    // Plain scrolls keep scrolling the surrounding UI.
    if (!e.ctrlKey) return;
    // Stop the browser/OS page zoom. The component attaches this listener
    // non-passively so preventDefault() is honoured.
    e.preventDefault();
    const frame = e.currentTarget as HTMLDivElement;
    if (!frame || frame.clientWidth === 0 || frame.clientHeight === 0) return;

    // Continuous focal zoom: factor 2 per ~100px of ctrl-scroll.
    const factor = 2 ** (-e.deltaY / 100);
    const target = clampZoom(this.zoom * factor, this.minZoom, this.maxZoom);
    if (!Number.isFinite(target) || target === this.zoom) return;
    const v = this.#clientToVirtual(frame, e.clientX, e.clientY);
    this.#anchorWorld(v.x, v.y, this.zoom, this.panX, this.panY, v.x, v.y, target);
    this.zoom = target;
  };
}
