/**
 * Modal scroll isolation: refcounted root/body locks compose across stacked
 * dialogs. Non-passive backdrop guards stop wheel and touch scroll chaining;
 * scrollable panels should also use `overscroll-behavior: contain`.
 *
 * Dialogs using this helper disable Bits UI's `preventScroll`: its body-only
 * lock does not cover the root or backdrop and its delayed style restoration
 * can reapply a stale overflow lock. See e2e/modal-scroll-lock.spec.ts.
 */

/** Minimal structural view of `document` (real documents satisfy this). */
export interface PageLike {
  documentElement: { style: { overflow: string } };
  body: { style: { overflow: string } };
}

let lockCount = 0;
let savedOverflow: { root: string; body: string } | null = null;

/**
 * Lock document scrolling (`overflow: hidden` on <html> and <body>).
 * Refcounted: nested/stacked locks compose and the page unlocks only when
 * the LAST lock is released. Returns an idempotent release callback that
 * restores the inline overflow values captured when the first lock was
 * taken.
 */
export function lockPageScroll(page: PageLike): () => void {
  if (lockCount === 0) {
    savedOverflow = {
      root: page.documentElement.style.overflow,
      body: page.body.style.overflow,
    };
    page.documentElement.style.overflow = "hidden";
    page.body.style.overflow = "hidden";
  }
  lockCount += 1;

  let released = false;
  return () => {
    if (released) return;
    released = true;
    lockCount = Math.max(0, lockCount - 1);
    if (lockCount === 0 && savedOverflow) {
      page.documentElement.style.overflow = savedOverflow.root;
      page.body.style.overflow = savedOverflow.body;
      savedOverflow = null;
    }
  };
}

/**
 * Decide whether a wheel/touchmove event that landed on `target` must be
 * blocked at the backdrop. Block by default (target outside the modal's
 * scrollable panel, or no panel known yet); allow only inside `scrollable`.
 * Pure so the semantics are unit-testable without a DOM. The panel param is
 * structurally typed (`contains`) so real Elements and test fakes both fit.
 */
export function blocksBackdropScroll(
  target: EventTarget | null,
  scrollable: { contains(node: unknown): boolean } | null | undefined,
): boolean {
  if (!scrollable || target === null) return true;
  return !scrollable.contains(target);
}

/**
 * Attach non-passive wheel + touchmove guards to a modal backdrop that
 * preventDefault() every event landing outside `scrollable` (the modal's
 * scrollable panel, when it has one; pass `null` to block the whole
 * overlay — right for dialogs with no scrollable region). Returns the
 * detach callback.
 */
export function attachBackdropScrollGuard(
  backdrop: HTMLElement,
  scrollable: HTMLElement | null | undefined,
): () => void {
  const onWheel = (e: WheelEvent) => {
    if (blocksBackdropScroll(e.target, scrollable)) e.preventDefault();
  };
  const onTouchMove = (e: TouchEvent) => {
    if (blocksBackdropScroll(e.target, scrollable)) e.preventDefault();
  };
  backdrop.addEventListener("wheel", onWheel, { passive: false });
  backdrop.addEventListener("touchmove", onTouchMove, { passive: false });
  return () => {
    backdrop.removeEventListener("wheel", onWheel);
    backdrop.removeEventListener("touchmove", onTouchMove);
  };
}
