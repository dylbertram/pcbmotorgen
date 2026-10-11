<script lang="ts">
  import { Dialog } from "bits-ui";
  import { GUIDE_TABS } from "../../guide/docs";
  import {
    attachBackdropScrollGuard,
    lockPageScroll,
  } from "../../utils/pageScrollLock";
  import Separator from "../ui/Separator.svelte";

  let { onClose, zIndex = 60 }: { onClose: () => void; zIndex?: number } = $props();

  let open = $state(true);
  let activeTabId = $state(GUIDE_TABS[0]?.id ?? "authoring");
  // Bits parts bind `ref` with a `null` fallback — the binding variables
  // must not be `undefined` or Svelte rejects it (props_invalid_value).
  let backdropRef: HTMLDivElement | null = $state(null);
  let panelRef: HTMLDivElement | null = $state(null);

  const activeTab = $derived(
    GUIDE_TABS.find((tab) => tab.id === activeTabId) ?? GUIDE_TABS[0],
  );

  function selectTab(id: string): void {
    activeTabId = id;
  }

  // Scroll lock (Kata xy31 precedent, same helpers as the upload modal):
  // refcounted overflow lock on <html>/<body> plus a non-passive backdrop
  // guard. Unlike the upload dialog, the guide panel DOES scroll — it is
  // passed as the guard's `scrollable` element, so wheel/touchmove inside
  // the panel scrolls the guide while everything on the dimmed backdrop is
  // blocked. Stacking over the upload modal composes: the page stays locked
  // until BOTH modals have closed. The Bits overlay and panel are the
  // backdrop/panel now (bound via bind:ref); Bits' own scroll lock is
  // disabled (preventScroll={false}) so this refcounted helper stays the
  // single source of truth the e2e suite asserts on.
  $effect(() => {
    const backdrop = backdropRef;
    if (!backdrop) return;
    const detachGuard = attachBackdropScrollGuard(backdrop, panelRef);
    const unlock = lockPageScroll(document);
    return () => {
      detachGuard();
      unlock();
    };
  });
</script>

<!-- Guide dialog — stacked above the upload panel (z-[60] > z-50).
     Escape closes only this topmost dialog: Bits UI tracks dialog layers
     globally, so the upload panel underneath stays open. -->
<Dialog.Root bind:open onOpenChange={(o) => { if (!o) onClose(); }}>
  <Dialog.Portal>
    <Dialog.Overlay bind:ref={backdropRef} style={`z-index: ${zIndex}`} class="fixed inset-0 z-[60] bg-black/70" />
    <Dialog.Content
      bind:ref={panelRef}
      preventScroll={false}
      aria-label="How to write a routing plugin"
      style={`z-index: ${zIndex}`}
      class="fixed left-1/2 top-1/2 z-[60] flex max-h-[85vh] w-full max-w-3xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-lg border border-slate-700 bg-slate-800 shadow-xl"
    >
      <!-- Header -->
      <div class="flex items-center justify-between border-b border-slate-700 px-4 py-3">
        <Dialog.Title class="text-sm font-semibold text-slate-100">
          How to write a routing plugin
        </Dialog.Title>
        <Dialog.Close
          aria-label="Close"
          class="rounded-md px-2 py-1 text-sm text-slate-400 transition-colors hover:bg-slate-700 hover:text-slate-100"
        >
          &times;
        </Dialog.Close>
      </div>

      <!-- Tabs -->
      <div
        role="tablist"
        aria-label="Guide sections"
        class="flex gap-1 overflow-x-auto border-b border-slate-700 px-3 pt-2"
      >
        {#each GUIDE_TABS as tab (tab.id)}
          <button
            type="button"
            role="tab"
            id="guide-tab-{tab.id}"
            aria-selected={tab.id === activeTabId}
            aria-controls="guide-panel"
            onclick={() => selectTab(tab.id)}
            class="whitespace-nowrap rounded-t-md border-b-2 px-3 py-2 text-xs font-semibold transition-colors
              {tab.id === activeTabId
              ? 'border-emerald-500 text-emerald-300'
              : 'border-transparent text-slate-400 hover:text-slate-100'}"
          >
            {tab.label}
          </button>
        {/each}
      </div>

      <!-- Scrollable guide body -->
      <div
        id="guide-panel"
        role="tabpanel"
        aria-labelledby="guide-tab-{activeTab?.id ?? 'authoring'}"
        class="guide-body min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4"
      >
        {@html activeTab?.html ?? ""}
      </div>

      <!-- Footer note -->
      <Separator />
      <div
        class="px-4 py-2 text-[10px] text-slate-500"
        role="note"
      >
        Bundled at build time from
        <code class="text-slate-400">crates/pcbmotorgen-routing/docs</code>
        — the same documents that define the plugin contract.
      </div>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>

<style>
  /*
   * Colors below are the default-Tailwind palette values (the tokens the
   * rest of the app uses via utility classes), inlined as hex so this block
   * does not depend on theme() resolution inside a Svelte <style> block.
   *
   * Typography for the markdown rendered from the crate docs. The content
   * is injected with {@html}, so the element selectors are :global — the
   * container itself stays scoped.
   */
  .guide-body {
    font-size: 0.8125rem;
    line-height: 1.55;
    color: #cbd5e1;
  }

  .guide-body :global(h1),
  .guide-body :global(h2),
  .guide-body :global(h3),
  .guide-body :global(h4) {
    color: #f1f5f9;
    font-weight: 600;
    margin: 1.25rem 0 0.5rem;
    line-height: 1.3;
  }

  .guide-body :global(h1) {
    font-size: 1.05rem;
    margin-top: 0;
  }

  .guide-body :global(h2) {
    font-size: 0.95rem;
    padding-bottom: 0.25rem;
    border-bottom: 1px solid #334155;
  }

  .guide-body :global(h3) {
    font-size: 0.875rem;
  }

  .guide-body :global(h4) {
    font-size: 0.8125rem;
  }

  .guide-body :global(p) {
    margin: 0.6rem 0;
  }

  .guide-body :global(a) {
    color: #34d399;
    text-decoration: underline;
  }

  .guide-body :global(ul),
  .guide-body :global(ol) {
    margin: 0.5rem 0;
    padding-left: 1.4rem;
  }

  .guide-body :global(ul) {
    list-style: disc;
  }

  .guide-body :global(ol) {
    list-style: decimal;
  }

  .guide-body :global(li) {
    margin: 0.25rem 0;
  }

  .guide-body :global(li input[type="checkbox"]) {
    margin-right: 0.35rem;
    vertical-align: middle;
  }

  .guide-body :global(code) {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    font-size: 0.75rem;
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 0.25rem;
    padding: 0.05rem 0.3rem;
    color: #e2e8f0;
  }

  .guide-body :global(pre) {
    margin: 0.75rem 0;
    padding: 0.75rem 0.9rem;
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 0.375rem;
    overflow-x: auto;
  }

  .guide-body :global(pre code) {
    background: transparent;
    border: none;
    padding: 0;
    font-size: 0.72rem;
    line-height: 1.5;
  }

  .guide-body :global(.md-link-ref) {
    color: #94a3b8;
  }

  .guide-body :global(blockquote) {
    margin: 0.75rem 0;
    padding: 0.25rem 0.9rem;
    border-left: 3px solid #f59e0b;
    background: rgba(245, 158, 11, 0.1);
    border-radius: 0 0.25rem 0.25rem 0;
  }

  .guide-body :global(blockquote p) {
    margin: 0.35rem 0;
    color: #fde68a;
  }

  .guide-body :global(table) {
    width: 100%;
    margin: 0.75rem 0;
    border-collapse: collapse;
    font-size: 0.72rem;
    display: block;
    overflow-x: auto;
  }

  .guide-body :global(th),
  .guide-body :global(td) {
    border: 1px solid #334155;
    padding: 0.3rem 0.55rem;
    text-align: left;
    vertical-align: top;
  }

  .guide-body :global(th) {
    background: #0f172a;
    color: #f1f5f9;
    font-weight: 600;
  }

  .guide-body :global(hr) {
    margin: 1rem 0;
    border: none;
    border-top: 1px solid #334155;
  }
</style>
