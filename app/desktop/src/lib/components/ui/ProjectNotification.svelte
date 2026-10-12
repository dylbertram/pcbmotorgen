<script lang="ts">
  let { message, onDismiss }: { message: string; onDismiss: () => void } = $props();

  function autoDismiss(node: HTMLDivElement): () => void {
    let timer: ReturnType<typeof setTimeout> | undefined;
    function pause(): void {
      clearTimeout(timer);
    }
    function resume(): void {
      pause();
      if (!node.isConnected || node.matches(":hover") || node.contains(document.activeElement)) return;
      timer = setTimeout(onDismiss, 4000);
    }
    function focusLeft(): void {
      // focusout fires before document.activeElement has switched.
      queueMicrotask(resume);
    }
    node.addEventListener("pointerenter", pause);
    node.addEventListener("pointerleave", resume);
    node.addEventListener("focusin", pause);
    node.addEventListener("focusout", focusLeft);
    resume();
    return () => {
      pause();
      node.removeEventListener("pointerenter", pause);
      node.removeEventListener("pointerleave", resume);
      node.removeEventListener("focusin", pause);
      node.removeEventListener("focusout", focusLeft);
    };
  }
</script>

<div
  {@attach autoDismiss}
  role="status"
  aria-live="polite"
  aria-atomic="true"
  aria-label="Project notification"
  class="fixed bottom-14 right-4 z-[140] flex w-fit max-w-[min(24rem,calc(100vw-2rem))] items-start gap-3 rounded-lg border border-slate-600 bg-slate-900 px-4 py-3 text-sm text-slate-100 shadow-xl"
>
  <svg aria-hidden="true" class="mt-0.5 shrink-0 text-emerald-400" width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="m3 8 3 3 7-7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" /></svg>
  <p class="min-w-0 break-words">{message}</p>
  <button type="button" onclick={onDismiss} aria-label="Dismiss notification" class="-mr-1 -mt-1 shrink-0 rounded px-1.5 py-0.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500">×</button>
</div>
