/**
 * DRC controller — extracted from App.svelte.
 *
 * Owns the interference-check state machine (violations / loading / error /
 * checkedLayoutKey) together with the generation + layout-key staleness
 * guards, so a DRC result computed for an older layout can never gate the
 * export panel for a newer one.
 *
 * The layout key is supplied as a callback (`getLayoutKey`) rather than a
 * value so reactivity keeps flowing through the caller's reactive context:
 * the caller reads `currentLayoutKey` / `ready` inside effects/deriveds and
 * the underlying config field reads are tracked there.
 */

import { checkCoilInterference } from "../ipc";
import { LatestAsyncTask } from "../utils/latestAsyncTask";
import type { CadGeometry, InterferenceViolation } from "../types";
import type { ConfigStore } from "./config.svelte";

interface DrcControllerOptions {
  /** Config store snapshot source — `checkCoilInterference(config.toIpc())`. */
  config: ConfigStore;
  /** Computes the layout fingerprint from the current config. */
  getLayoutKey: () => string;
  /** Imported copper to check instead of the generated layout. */
  getCadGeometry?: () => CadGeometry | null;
}

export class DrcController {
  violations = $state<InterferenceViolation[]>([]);
  loading = $state(false);
  error = $state<string | null>(null);
  checkedLayoutKey = $state<string | null>(null);

  constructor(options: DrcControllerOptions) {
    this.config = options.config;
    this.getLayoutKey = options.getLayoutKey;
    this.getCadGeometry = options.getCadGeometry ?? (() => null);
  }

  readonly #schedule = new LatestAsyncTask<string, InterferenceViolation[]>({
    delayMs: 300,
    run: () => checkCoilInterference(this.config.toIpc(), this.getCadGeometry()),
    onResult: (result, layoutKey) => {
      if (layoutKey !== this.currentLayoutKey) return;
      this.violations = result;
      this.checkedLayoutKey = layoutKey;
      this.loading = false;
    },
    onError: (reason, layoutKey) => {
      if (layoutKey !== this.currentLayoutKey) return;
      this.error = reason instanceof Error ? reason.message : String(reason);
      this.loading = false;
    },
  });

  private readonly config: ConfigStore;
  private readonly getLayoutKey: () => string;
  private readonly getCadGeometry: () => CadGeometry | null;

  /** The layout fingerprint for the current config, recomputed live. */
  get currentLayoutKey(): string {
    return this.getLayoutKey();
  }

  /**
   * True when the latest completed DRC check applies to the exact current
   * layout — mirrors the old `drcReady` derived in App.svelte.
   */
  get ready(): boolean {
    return (
      !this.loading &&
      this.error === null &&
      this.checkedLayoutKey !== null &&
      this.checkedLayoutKey === this.currentLayoutKey
    );
  }

  /** Invalidate immediately, but never pile up native checks during edits. */
  request(): void {
    const layoutKey = this.currentLayoutKey;
    this.loading = true;
    this.error = null;
    this.violations = [];
    this.checkedLayoutKey = null;
    this.#schedule.request(layoutKey);
  }

  cancel(): void {
    this.#schedule.cancel();
    this.loading = false;
    this.error = null;
    this.violations = [];
    this.checkedLayoutKey = null;
  }
}
