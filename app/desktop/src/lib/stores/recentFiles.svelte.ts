/**
 * Open Recent state (kata eap8) — the most-recent-first list of opened
 * `.pmproj` files backing the native File > Open Recent submenu.
 *
 * Ownership & flow: the webview owns the list and its persistence; the
 * native menu is a mirror. Mutations (open, clear, prune) persist to
 * localStorage and are pushed to the menu via the `set_recent_files`
 * command; menu clicks flow back as `menu:*` events (see
 * `bindProjectMenuActions`) into `ProjectStore.openPath`.
 *
 * Persistence choice: localStorage — synchronous lazy load (no async
 * dependency before the first menu sync), no extra capability/permission
 * changes, trivial to unit-test, and it persists across restarts of the
 * packaged WKWebView-based app.
 *
 * Pruning: missing files are dropped on ACCESS (first menu sync after
 * load, and immediately before re-opening an entry) — never as a
 * background startup scan of the filesystem.
 *
 * Port contract: `RecentFilesPort` implementations must not reject — they
 * degrade gracefully (keep the entry / skip the best-effort menu refresh)
 * so recents can never interfere with the open/save flows.
 */

import { fileExists, setRecentFiles } from "../ipc";

/** Hard cap on the recents list (most-recent-first). */
export const MAX_RECENT_FILES = 10;

/** Environment port the store talks through (injected — unit-testable). */
export interface RecentFilesPort {
  /** Persisted list, or `null` when never stored / unreadable. */
  load(): Promise<string[] | null>;
  /** Best-effort persist of the current list. Never rejects. */
  persist(paths: string[]): Promise<void>;
  /** Disk existence check; fails OPEN (true on doubt) so nothing is pruned on a backend hiccup. */
  exists(path: string): Promise<boolean>;
  /** Best-effort mirror of the list into the native File menu. Never rejects. */
  syncMenu(paths: string[]): Promise<void>;
}

export class RecentFilesStore {
  /** Absolute file paths, most-recent-first, capped at {@link MAX_RECENT_FILES}. */
  paths = $state<string[]>([]);

  /** Set on first load; reset if loading rejected so it can be retried. */
  private loadPromise: Promise<void> | null = null;

  constructor(private port: RecentFilesPort) {}

  /** Lazily load the persisted list once; the first load is an access, so it prunes dead entries before syncing the menu. */
  async load(): Promise<void> {
    await this.ensureLoaded();
  }

  /** Record a successfully opened file: dedupe by moving to front, cap, persist, sync menu. */
  async record(path: string): Promise<void> {
    await this.ensureLoaded();
    this.paths = [path, ...this.paths.filter((p) => p !== path)].slice(
      0,
      MAX_RECENT_FILES,
    );
    await this.sync();
  }

  /** Drop one entry (e.g. a vanished file); no-op when absent. */
  async remove(path: string): Promise<void> {
    if (!this.paths.includes(path)) return;
    this.paths = this.paths.filter((p) => p !== path);
    await this.sync();
  }

  /** Drop every entry; the menu shows its empty/disabled state. */
  async clear(): Promise<void> {
    await this.ensureLoaded();
    this.paths = [];
    await this.sync();
  }

  /**
   * Prune every entry whose file no longer exists on disk and return the
   * pruned paths. Called on access (first menu build) — deliberately NOT
   * wired to app startup beyond that.
   */
  async pruneMissing(): Promise<string[]> {
    await this.ensureLoaded();
    const missing = await this.pruneNow();
    return missing;
  }

  /**
   * Pre-open hook for a recents entry: drop it if its file vanished, then
   * the caller proceeds anyway — `ProjectStore.openPath` surfaces the
   * existing backend "Open failed — could not open …: file not found" UX.
   */
  async dropMissing(path: string): Promise<void> {
    await this.ensureLoaded();
    if (this.paths.includes(path) && !(await this.port.exists(path))) {
      await this.remove(path);
    }
  }

  /** Single-load guard; concurrent callers share the same promise. */
  private ensureLoaded(): Promise<void> {
    if (this.loadPromise === null) {
      this.loadPromise = (async () => {
        const stored = await this.port.load();
        if (Array.isArray(stored)) {
          this.paths = stored
            .filter((p) => typeof p === "string" && p.length > 0)
            .slice(0, MAX_RECENT_FILES);
        }
        // Loading IS an access: the initial menu build prunes entries whose
        // file disappeared since the last run (not a background scan —
        // bounded to the ≤10 stored entries).
        const missing = await this.pruneNow();
        // The native menu starts empty on every launch, even when the stored
        // list is unchanged. Pruning already syncs when it removes entries.
        if (missing.length === 0) await this.port.syncMenu(this.paths);
      })().catch((e) => {
        this.loadPromise = null; // allow a retry on the next access
        throw e;
      });
    }
    return this.loadPromise;
  }

  /** Exists-check each entry; persist+sync only when something was dropped. */
  private async pruneNow(): Promise<string[]> {
    const checks = await Promise.all(
      this.paths.map(async (path) => ({
        path,
        present: await this.port.exists(path),
      })),
    );
    const missing = checks.filter((c) => !c.present).map((c) => c.path);
    if (missing.length === 0) return [];
    const dead = new Set(missing);
    this.paths = this.paths.filter((p) => !dead.has(p));
    await this.sync();
    return missing;
  }

  /** Persist the current list, then mirror it into the native menu. */
  private async sync(): Promise<void> {
    await this.port.persist(this.paths);
    await this.port.syncMenu(this.paths);
  }
}

// ---------------------------------------------------------------------------
// Live webview port (localStorage + Tauri commands) and module singleton.
// ---------------------------------------------------------------------------

const STORAGE_KEY = "pcbmotorgen.recentProjects";

/** Live port: localStorage persistence, invoke-backed menu sync + exists check. */
const livePort: RecentFilesPort = {
  async load(): Promise<string[] | null> {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw === null) return null;
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return null;
      return parsed.filter((p): p is string => typeof p === "string");
    } catch {
      return null; // corrupt or inaccessible storage → start empty
    }
  },
  async persist(paths: string[]): Promise<void> {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(paths));
    } catch {
      // Quota/full/decayed storage — the menu still reflects the session's
      // list; persistence resumes when storage recovers.
    }
  },
  async exists(path: string): Promise<boolean> {
    try {
      return await fileExists(path); // ipc wrapper returns true outside Tauri
    } catch {
      return true; // fail open — never prune on a backend hiccup
    }
  },
  async syncMenu(paths: string[]): Promise<void> {
    try {
      await setRecentFiles(paths);
    } catch {
      // Best effort: an unavailable/older backend keeps the stale menu; the
      // entries remain reachable because opens always flow via loadProject.
    }
  },
};

/** App-wide singleton (same pattern as `config`). */
export const recentFiles = new RecentFilesStore(livePort);
