import { describe, expect, it, vi } from "vitest";
import {
  MAX_RECENT_FILES,
  RecentFilesStore,
  type RecentFilesPort,
} from "./recentFiles.svelte";

/**
 * Unit coverage of the Open Recent store (kata eap8): ordering, dedupe,
 * cap, prune-on-access and clear — all against a mocked persistence/menu
 * port (no Tauri, no localStorage, no disk).
 */

interface FakePortOptions {
  /** List returned by `load` (persisted list from a previous session). */
  stored?: string[] | null;
  /** Disk-existence verdict per path (default: everything exists). */
  exists?: (path: string) => boolean;
}

function makePort(options: FakePortOptions = {}): RecentFilesPort & {
  persistCalls: string[][];
  syncCalls: string[][];
} {
  const persistCalls: string[][] = [];
  const syncCalls: string[][] = [];
  return {
    persistCalls,
    syncCalls,
    load: vi.fn(async () =>
      options.stored === undefined ? null : [...options.stored!],
    ),
    persist: vi.fn(async (paths: string[]) => {
      persistCalls.push([...paths]);
    }),
    exists: vi.fn(async (path: string) =>
      options.exists ? options.exists(path) : true,
    ),
    syncMenu: vi.fn(async (paths: string[]) => {
      syncCalls.push([...paths]);
    }),
  };
}

describe("RecentFilesStore — load", () => {
  it("no persisted list: syncs the disabled menu without rewriting storage", async () => {
    const port = makePort();
    const store = new RecentFilesStore(port);
    await store.load();
    expect(store.paths).toEqual([]);
    expect(port.syncCalls).toEqual([[]]);
    expect(port.persistCalls).toEqual([]);
  });

  it("an explicitly-empty stored list is still accepted as empty", async () => {
    const port = makePort({ stored: [] });
    const store = new RecentFilesStore(port);
    await store.load();
    expect(store.paths).toEqual([]);
    expect(port.syncCalls).toEqual([[]]);
  });

  it("loads the persisted list most-recent-first and drops malformed entries", async () => {
    const port = makePort({
      stored: ["/b.pmproj", "", "/a.pmproj", 42 as unknown as string],
    });
    const store = new RecentFilesStore(port);
    await store.load();
    expect(store.paths).toEqual(["/b.pmproj", "/a.pmproj"]);
    expect(port.syncCalls).toEqual([["/b.pmproj", "/a.pmproj"]]);
    expect(port.persistCalls).toEqual([]);
  });

  it("syncs an unchanged persisted list once, including concurrent startup loads", async () => {
    const port = makePort({ stored: ["/live.pmproj"] });
    const store = new RecentFilesStore(port);
    await Promise.all([store.load(), store.load()]);
    await store.load();
    expect(port.syncCalls).toEqual([["/live.pmproj"]]);
    expect(port.persistCalls).toEqual([]);
    expect(port.load).toHaveBeenCalledTimes(1);
  });

  it("prunes persisted entries whose file vanished on the first access", async () => {
    const port = makePort({
      stored: ["/new.pmproj", "/deleted.pmproj", "/old.pmproj"],
      exists: (p) => p !== "/deleted.pmproj",
    });
    const store = new RecentFilesStore(port);
    await store.load();
    expect(store.paths).toEqual(["/new.pmproj", "/old.pmproj"]);
    expect(port.persistCalls).toEqual([["/new.pmproj", "/old.pmproj"]]);
    expect(port.syncCalls).toEqual([["/new.pmproj", "/old.pmproj"]]);
  });

  it("disables the menu if every persisted project has vanished", async () => {
    const port = makePort({ stored: ["/deleted.pmproj"], exists: () => false });
    const store = new RecentFilesStore(port);
    await store.load();
    expect(store.paths).toEqual([]);
    expect(port.syncCalls).toEqual([[]]);
    expect(port.persistCalls).toEqual([[]]);
  });
});

describe("RecentFilesStore — record", () => {
  it("records most-recent-first", async () => {
    const port = makePort();
    const store = new RecentFilesStore(port);
    await store.record("/a.pmproj");
    await store.record("/b.pmproj");
    expect(store.paths).toEqual(["/b.pmproj", "/a.pmproj"]);
  });

  it("dedupes by moving an existing entry to the front", async () => {
    const port = makePort();
    const store = new RecentFilesStore(port);
    await store.record("/a.pmproj");
    await store.record("/b.pmproj");
    await store.record("/c.pmproj");
    expect(store.paths).toEqual(["/c.pmproj", "/b.pmproj", "/a.pmproj"]);

    await store.record("/a.pmproj");
    expect(store.paths).toEqual(["/a.pmproj", "/c.pmproj", "/b.pmproj"]);
  });

  it("caps the list at MAX_RECENT_FILES, evicting the oldest", async () => {
    expect(MAX_RECENT_FILES).toBe(10);
    const port = makePort();
    const store = new RecentFilesStore(port);
    for (let i = 0; i < MAX_RECENT_FILES + 2; i++) {
      await store.record(`/motor-${i}.pmproj`);
    }
    expect(store.paths).toHaveLength(MAX_RECENT_FILES);
    expect(store.paths).toEqual([
      "/motor-11.pmproj",
      "/motor-10.pmproj",
      "/motor-9.pmproj",
      "/motor-8.pmproj",
      "/motor-7.pmproj",
      "/motor-6.pmproj",
      "/motor-5.pmproj",
      "/motor-4.pmproj",
      "/motor-3.pmproj",
      "/motor-2.pmproj",
    ]);
  });

  it("merges into the persisted list: re-opens move to front", async () => {
    const port = makePort({ stored: ["/a.pmproj", "/b.pmproj"] });
    const store = new RecentFilesStore(port);
    await store.record("/b.pmproj");
    expect(store.paths).toEqual(["/b.pmproj", "/a.pmproj"]);
  });

  it("every record persists and syncs the menu", async () => {
    const port = makePort();
    const store = new RecentFilesStore(port);
    await store.record("/a.pmproj");
    expect(port.persistCalls).toEqual([["/a.pmproj"]]);
    expect(port.syncCalls).toEqual([[], ["/a.pmproj"]]);
  });
});

describe("RecentFilesStore — remove/clear", () => {
  it("remove() ignores unknown paths", async () => {
    const port = makePort();
    const store = new RecentFilesStore(port);
    await store.record("/a.pmproj");
    await store.remove("/not-listed.pmproj");
    expect(store.paths).toEqual(["/a.pmproj"]);
  });

  it("clear() empties the list, then persists and syncs the empty state", async () => {
    const port = makePort();
    const store = new RecentFilesStore(port);
    await store.record("/a.pmproj");
    await store.record("/b.pmproj");

    await store.clear();
    expect(store.paths).toEqual([]);
    expect(port.syncCalls.at(-1)).toEqual([]);
  });
});
