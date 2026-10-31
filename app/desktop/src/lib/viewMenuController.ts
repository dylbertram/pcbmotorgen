import { listenViewMenu, publishViewMenu } from "./ipc/viewMenu";
import type { ViewMenuAction, ViewMenuItemState, ViewMenuState } from "./viewMenu";

/** One native menu, one active viewport. Publications are serialized/latest-only. */
export class ViewMenuController {
  #owner: string | null = null;
  #queued: ViewMenuState | null = null;
  #running = false;
  constructor(
    private publish: (state: ViewMenuState) => Promise<void>,
    private subscribe: (handler: (action: ViewMenuAction) => void) => Promise<() => void>,
  ) {}

  connect(read: () => ViewMenuItemState[], apply: (id: string) => void) {
    // getRandomValues also works on custom-scheme desktop webviews.
    const owner = `viewport-${Array.from(crypto.getRandomValues(new Uint32Array(4)), n => n.toString(16)).join("-")}`;
    this.#owner = owner;
    let disposed = false;
    let unlisten: (() => void) | undefined;
    const update = () => {
      if (!disposed && this.#owner === owner) this.#enqueue({ owner, items: read() });
    };
    void this.subscribe((action) => {
      if (disposed || this.#owner !== owner || action.owner !== owner) return;
      if (!read().some((item) => item.id === action.id && item.enabled)) return;
      apply(action.id);
      // Native check items toggle themselves even on an already-selected radio.
      update();
    }).then((cleanup) => { if (disposed) cleanup(); else unlisten = cleanup; })
      .catch((error) => console.error("Could not listen to the View menu", error));
    return {
      update,
      dispose: () => {
        disposed = true;
        unlisten?.();
        if (this.#owner !== owner) return;
        this.#owner = null;
        this.#enqueue({ owner: null, items: read().map((item) => ({ ...item, checked: false, enabled: false })) });
      },
    };
  }

  #enqueue(state: ViewMenuState): void {
    this.#queued = state;
    if (!this.#running) void this.#drain();
  }
  async #drain(): Promise<void> {
    this.#running = true;
    try {
      while (this.#queued) {
        const state = this.#queued;
        this.#queued = null;
        try { await this.publish(state); }
        catch (error) { console.error("Could not synchronize the View menu", error); }
      }
    } finally { this.#running = false; }
  }
}

export const nativeViewMenu = new ViewMenuController(publishViewMenu, listenViewMenu);
