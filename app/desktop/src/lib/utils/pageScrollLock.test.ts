import { describe, it, expect } from "vitest";
import {
  lockPageScroll,
  blocksBackdropScroll,
  type PageLike,
} from "./pageScrollLock";

/** Fake page: records overflow writes on <html> and <body>. */
function makePage(initial: { root?: string; body?: string } = {}): PageLike & {
  rootOverflow: () => string;
  bodyOverflow: () => string;
} {
  const root = { style: { overflow: initial.root ?? "" } };
  const body = { style: { overflow: initial.body ?? "" } };
  return {
    documentElement: root,
    body,
    rootOverflow: () => root.style.overflow,
    bodyOverflow: () => body.style.overflow,
  };
}

describe("lockPageScroll", () => {
  it("sets overflow hidden on <html> and <body>", () => {
    const page = makePage();
    const unlock = lockPageScroll(page);
    expect(page.rootOverflow()).toBe("hidden");
    expect(page.bodyOverflow()).toBe("hidden");
    unlock();
  });

  it("restores the previous inline values on release", () => {
    const page = makePage({ root: "auto", body: "scroll" });
    const unlock = lockPageScroll(page);
    expect(page.rootOverflow()).toBe("hidden");
    unlock();
    expect(page.rootOverflow()).toBe("auto");
    expect(page.bodyOverflow()).toBe("scroll");
  });

  it("restores to empty string when nothing was set before", () => {
    const page = makePage();
    const unlock = lockPageScroll(page);
    unlock();
    expect(page.rootOverflow()).toBe("");
    expect(page.bodyOverflow()).toBe("");
  });

  it("is refcounted: the page stays locked until the LAST release", () => {
    const page = makePage();
    const unlockA = lockPageScroll(page);
    const unlockB = lockPageScroll(page);

    unlockA();
    expect(page.rootOverflow()).toBe("hidden"); // B still holds the lock
    expect(page.bodyOverflow()).toBe("hidden");

    unlockB();
    expect(page.rootOverflow()).toBe("");
    expect(page.bodyOverflow()).toBe("");
  });

  it("is order-safe for stacked modals opened and closed in any order", () => {
    const page = makePage({ root: "", body: "" });
    const unlockA = lockPageScroll(page);
    const unlockB = lockPageScroll(page);
    unlockB(); // close out of open order
    expect(page.rootOverflow()).toBe("hidden"); // A still open
    unlockA();
    expect(page.rootOverflow()).toBe("");
  });

  it("release callbacks are idempotent", () => {
    const page = makePage();
    const unlock = lockPageScroll(page);
    unlock();
    unlock();
    expect(page.rootOverflow()).toBe("");
  });

  it("re-locking after a full release snapshots the fresh state", () => {
    const page = makePage();
    const unlockA = lockPageScroll(page);
    unlockA();

    page.documentElement.style.overflow = "clip"; // stylesheet/app changed it
    const unlockB = lockPageScroll(page);
    expect(page.rootOverflow()).toBe("hidden");
    unlockB();
    expect(page.rootOverflow()).toBe("clip");
  });
});

describe("blocksBackdropScroll", () => {
  // Stand-in event targets: the panel only compares identity.
  const inside = {} as EventTarget;
  const outside = {} as EventTarget;
  const panel = { contains: (node: unknown) => node === inside };

  it("blocks when the event landed outside the scrollable panel", () => {
    expect(blocksBackdropScroll(outside, panel)).toBe(true);
  });

  it("allows events inside the panel so it can scroll itself", () => {
    expect(blocksBackdropScroll(inside, panel)).toBe(false);
  });

  it("blocks by default when no panel is known yet", () => {
    expect(blocksBackdropScroll(inside, null)).toBe(true);
    expect(blocksBackdropScroll(inside, undefined)).toBe(true);
  });

  it("blocks a null target", () => {
    expect(blocksBackdropScroll(null, panel)).toBe(true);
  });
});
