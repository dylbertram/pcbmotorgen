<script lang="ts">
  import type { InterferenceViolation } from "../../types";
  import ScrollArea from "../ui/ScrollArea.svelte";

  let {
    violations,
    loading,
    error,
    ready,
    onCheck,
  }: {
    violations: InterferenceViolation[];
    loading: boolean;
    error: string | null;
    ready: boolean;
    onCheck: () => void;
  } = $props();

  let shown = $derived(violations.slice(0, 50));

  function violationKey(violation: InterferenceViolation): string {
    return [
      violation.layer,
      violation.net_a,
      violation.net_b,
      violation.kind,
      violation.gap_mm,
      violation.message,
    ].join("::");
  }
</script>

<div class="space-y-3" aria-labelledby="interference-heading">
  <div class="flex items-center justify-between">
    <h2 id="interference-heading" class="text-xs font-semibold uppercase tracking-wider text-slate-300">
      Core interference check (DRC)
    </h2>
    <button
      type="button"
      onclick={onCheck}
      disabled={loading}
      class="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-60 transition-colors"
    >
      {loading ? "Checking…" : "Check layout"}
    </button>
  </div>

  {#if loading}
    <div
      class="rounded-md border border-sky-500/50 bg-sky-500/10 px-3 py-2 text-sm text-sky-200"
      role="status"
      aria-live="polite"
    >
      Checking the current layout…
    </div>
  {:else if error}
    <div
      class="rounded-md border border-rose-500/60 bg-rose-500/10 px-3 py-2 text-sm text-rose-200 whitespace-pre-wrap break-words"
      role="alert"
      aria-live="assertive"
    >
      DRC could not complete: {error}
    </div>
  {:else if !ready}
    <div
      class="rounded-md border border-amber-500/60 bg-amber-500/10 px-3 py-2 text-sm text-amber-200"
      role="status"
      aria-live="polite"
    >
      DRC is waiting for a completed check of the current layout.
    </div>
  {:else if violations.length === 0}
    <div
      class="rounded-md border border-emerald-500/60 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200"
      role="status"
      aria-live="polite"
    >
      No clearance violations &mdash; current layout is clean.
    </div>
  {:else}
    <div
      class="rounded-md border border-amber-500/60 bg-amber-500/10 px-3 py-2 text-sm text-amber-200"
      role="alert"
      aria-live="assertive"
    >
      {violations.length} violation{violations.length === 1 ? "" : "s"} detected
      {violations.length > shown.length ? ` · showing first ${shown.length}` : ""}
    </div>
    <ScrollArea class="max-h-64" viewportClass="pr-1">
      <ul class="space-y-2 pr-1" aria-label="DRC violations">
        {#each shown as violation (violationKey(violation))}
          <li
            class="rounded-md bg-slate-800/60 border border-amber-500/40 px-3 py-2 text-xs"
            title={violation.message}
          >
            <div class="flex items-center justify-between gap-2 text-amber-200">
              <span class="font-mono">
                L{violation.layer} &middot; {violation.net_a} ↔ {violation.net_b}
              </span>
              <span class="font-mono whitespace-nowrap">{violation.gap_mm.toFixed(2)} mm</span>
            </div>
            <div class="mt-1 text-slate-300">
              <span class="uppercase text-[10px] tracking-wider text-amber-400/80">
                {violation.kind}
              </span>
              <span class="text-slate-400"> &middot; {violation.message}</span>
            </div>
          </li>
        {/each}
      </ul>
    </ScrollArea>
  {/if}
</div>
