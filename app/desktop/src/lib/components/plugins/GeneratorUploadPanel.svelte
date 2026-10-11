<script lang="ts">
  import { Dialog } from "bits-ui";
  import type { ConfigStore } from "../../stores/config.svelte";
  import {
    openFileDialog,
    registerRoutingPlugin,
  } from "../../ipc";
  import { attachBackdropScrollGuard, lockPageScroll } from "../../utils/pageScrollLock";
  import PluginAuthoringGuideModal from "./PluginAuthoringGuideModal.svelte";

  let {
    config,
    onClose,
    onLoaded,
    zIndex = 50,
  }: {
    config: ConfigStore;
    onClose: () => void;
    onLoaded?: (id: string) => void;
    zIndex?: number;
  } = $props();

  let open = $state(true);
  let path = $state("");
  let name = $state("");
  let status = $state<"idle" | "loading" | "success" | "error">("idle");
  let message = $state("");
  // Bits parts bind `ref` with a `null` fallback — the binding variable must
  // not be `undefined` or Svelte rejects it (props_invalid_value).
  let backdropRef: HTMLDivElement | null = $state(null);

  // The in-app plugin authoring guide (kata bprp), stacked ABOVE this
  // dialog. While it is open, Escape must close only the guide — Bits UI
  // tracks dialog layers globally, so the topmost dialog consumes Escape
  // and closes only itself.
  let guideOpen = $state(false);

  const KIND_LABEL: Record<"native" | "python", string> = {
    native: "Native crate plugin (.dylib / .so / .dll)",
    python: "Python runner (.py)",
  };

  const pathBasename = $derived(
    path ? path.split(/[\\/]/).pop() || path : "",
  );

  /**
   * Infer the plugin kind from the chosen file's extension. Native crates
   * ship as shared libraries (.dylib for macOS / .so for Linux / .dll for
   * Windows); Python runners are .py. Returns `null` for unrecognised
   * extensions.
   */
  function inferKind(filePath: string): "native" | "python" | null {
    const ext = (filePath.split(".").pop() || "").toLowerCase();
    if (ext === "py") return "python";
    if (ext === "dylib" || ext === "so" || ext === "dll" || ext === "cdylib") {
      return "native";
    }
    return null;
  }

  const inferredKind = $derived(path ? inferKind(path) : null);

  async function browse(): Promise<void> {
    try {
      const picked = await openFileDialog();
      if (picked) {
        path = picked;
        status = "idle";
        message = "";
      }
    } catch (e) {
      status = "error";
      message = e instanceof Error ? e.message : String(e);
    }
  }

  async function handleLoad(): Promise<void> {
    if (!path) {
      status = "error";
      message = "Browse for a generator file first.";
      return;
    }
    const kind = inferKind(path);
    if (!kind) {
      status = "error";
      message =
        "Unrecognized file type — expected .py (Python runner) or .dylib / .so / .dll (native crate plugin).";
      return;
    }
    status = "loading";
    message = "";
    try {
      const newId = await registerRoutingPlugin(
        kind,
        path,
        name.trim() || null,
        config.toIpc(),
      );
      // Reload the pattern catalog (which also re-registers persisted
      // plugins on the backend), then select the fresh pattern and pull its
      // declared parameters.
      await config.loadRoutingPatterns();
      config.routing_pattern = newId;
      await config.loadRoutingParams(newId);
      status = "success";
      message = `Registered "${newId}". Selected and ready.`;
      onLoaded?.(newId);
      onClose();
    } catch (e) {
      status = "error";
      message = e instanceof Error ? e.message : String(e);
    }
  }

  // Scroll lock (Kata xy31): nothing inside this dialog scrolls natively,
  // so every wheel/touchmove on the overlay is blocked and the document is
  // overflow-locked while the dialog is open — the page behind can never
  // scroll. The Bits overlay IS the backdrop now (bound via bind:ref);
  // Bits' own scroll lock is disabled (preventScroll={false}) so this
  // refcounted helper stays the single source of truth the e2e suite
  // asserts on.
  $effect(() => {
    const backdrop = backdropRef;
    if (!backdrop) return;
    const detachGuard = attachBackdropScrollGuard(backdrop, null);
    const unlock = lockPageScroll(document);
    return () => {
      detachGuard();
      unlock();
    };
  });
</script>

<Dialog.Root bind:open onOpenChange={(o) => { if (!o) onClose(); }}>
  <Dialog.Portal>
    <Dialog.Overlay
      bind:ref={backdropRef}
      class="fixed inset-0 z-50 bg-black/60"
      style={`z-index: ${zIndex}`}
    />
    <Dialog.Content
      preventScroll={false}
      aria-label="Load new generator"
      style={`z-index: ${zIndex}`}
      class="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-slate-700 bg-slate-800 shadow-xl"
    >
      <!-- Header -->
      <div class="flex items-center justify-between border-b border-slate-700 px-4 py-3">
        <Dialog.Title class="text-sm font-semibold text-slate-100">Load new generator</Dialog.Title>
        <Dialog.Close
          disabled={status === "loading"}
          aria-label="Close"
          class="rounded-md px-2 py-1 text-slate-400 hover:text-slate-100 hover:bg-slate-700 text-sm transition-colors disabled:opacity-60"
        >&times;</Dialog.Close>
      </div>

      <!-- Body -->
      <div class="space-y-3 px-4 py-4">
        <!-- File browser -->
        <div>
          <span class="block text-xs text-slate-400 mb-1">
            Generator file
            <span class="text-slate-600"> — .py or native plugin (.dylib / .so / .dll)</span>
          </span>
          <div class="flex items-center gap-2">
            <span
              class="flex-1 truncate rounded-md bg-slate-900 border border-slate-700 px-3 py-2 text-sm font-mono text-slate-400"
              title={path || ""}
            >
              {pathBasename || "No file selected"}
            </span>
            <button
              type="button"
              onclick={browse}
              disabled={status === "loading"}
              class="shrink-0 rounded-md bg-slate-700 hover:bg-slate-600 disabled:opacity-60 px-3 py-2 text-sm font-semibold text-white transition-colors"
            >
              Browse…
            </button>
          </div>
        </div>

        {#if inferredKind}
          <div class="flex items-center gap-2 text-[11px]">
            <span
              class="rounded px-1.5 py-0.5 font-semibold uppercase tracking-wider {inferredKind ===
              'native'
                ? 'bg-sky-500/20 text-sky-300'
                : 'bg-amber-500/20 text-amber-300'}"
            >
              {KIND_LABEL[inferredKind]}
            </span>
            <span class="text-slate-500">inferred from file type</span>
          </div>
        {/if}

        <!-- Pattern name -->
        <label class="block">
          <span class="block text-xs text-slate-400 mb-1">
            Pattern name <span class="text-slate-600">(optional — defaults to plugin's own id)</span>
          </span>
          <input
            type="text"
            bind:value={name}
            placeholder="e.g. my-braid"
            spellcheck="false"
            disabled={status === "loading"}
            class="w-full rounded-md bg-slate-900 border border-slate-700 px-3 py-2 text-sm font-mono text-slate-100 focus:outline-none focus:border-emerald-500 disabled:opacity-60"
          />
        </label>

        {#if status === "error"}
          <div class="rounded-md border border-rose-500/60 bg-rose-500/10 px-3 py-2 text-sm text-rose-200 whitespace-pre-wrap break-words">
            {message}
          </div>
        {:else if status === "success"}
          <div class="rounded-md border border-emerald-500/60 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200">
            {message}
          </div>
        {:else if status === "loading"}
          <p class="text-xs text-slate-400 animate-pulse">Probing generator against the current layout…</p>
        {/if}

        <!-- Actions -->
        <div class="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onclick={() => (guideOpen = true)}
            aria-haspopup="dialog"
            title="Open the plugin authoring guide bundled from the routing crate docs"
            class="mr-auto rounded-md px-2 py-2 text-xs font-medium text-emerald-400 hover:text-emerald-300 hover:bg-slate-700 transition-colors"
          >
            How to write a plugin?
          </button>
          <Dialog.Close
            disabled={status === "loading"}
            class="rounded-md px-3 py-2 text-sm font-semibold text-slate-300 hover:text-slate-100 hover:bg-slate-700 transition-colors disabled:opacity-60"
          >
            Cancel
          </Dialog.Close>
          <button
            type="button"
            onclick={handleLoad}
            disabled={status === "loading" || !path}
            class="rounded-md bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 disabled:cursor-not-allowed px-3 py-2 text-sm font-semibold text-white transition-colors"
          >
            {status === "loading" ? "Loading…" : "Load generator"}
          </button>
        </div>
      </div>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>

<!-- Stacked plugin authoring guide (kata bprp). Sibling of the upload
     dialog (outside its Dialog.Root) so it paints above it; the
     refcounted scroll lock composes. -->
{#if guideOpen}
  <PluginAuthoringGuideModal zIndex={zIndex + 10} onClose={() => (guideOpen = false)} />
{/if}
