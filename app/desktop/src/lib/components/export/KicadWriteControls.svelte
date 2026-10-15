<script lang="ts">
  import type { KicadWriteResult } from "../../types";

  let {
    dryRun,
    writing,
    connected,
    writeResult,
    drcReady,
    drcError,
    overrideDrc,
    zeroItemWrite,
    toast,
    dryRunPreview,
    drcViolationCount,
    drcGateBlocked,
    drcGateMessage,
    onToggleDryRun,
    onDrcOverrideChange,
    onWrite,
  }: {
    dryRun: boolean;
    writing: boolean;
    connected: boolean;
    writeResult: KicadWriteResult | null;
    drcReady: boolean;
    drcError: string | null;
    overrideDrc: boolean;
    zeroItemWrite: boolean;
    toast: string | null;
    dryRunPreview: string | null;
    drcViolationCount: number;
    drcGateBlocked: boolean;
    drcGateMessage: string;
    onToggleDryRun: (event: Event) => void;
    onDrcOverrideChange: (event: Event) => void;
    onWrite: () => void;
  } = $props();
</script>

<div class="space-y-3">
  <!-- Export gate: both dry-run and real writes use this DRC gate. -->
  <div class="space-y-2">
    <label class="flex cursor-pointer select-none items-center gap-2 text-xs text-slate-300">
      <input
        type="checkbox"
        checked={overrideDrc}
        onchange={onDrcOverrideChange}
        class="h-3.5 w-3.5 rounded border-slate-600 bg-slate-900 accent-amber-500"
      />
      <span>Override DRC — acknowledge</span>
    </label>

    {#if overrideDrc}
      <div
        class="rounded-md border border-amber-500/70 bg-amber-500/10 px-3 py-2 text-xs text-amber-100"
        role="alert"
        aria-live="assertive"
      >
        DRC override acknowledged for this session. {drcViolationCount} violation{drcViolationCount === 1 ? "" : "s"} are currently reported.
        {#if !drcReady}
          The current-layout check is not complete; export is proceeding by acknowledgement.
        {/if}
      </div>
    {:else if drcGateBlocked}
      <div
        class="rounded-md border border-amber-500/60 bg-amber-500/10 px-3 py-2 text-xs text-amber-200"
        role={drcError ? "alert" : "status"}
        aria-live={drcError ? "assertive" : "polite"}
      >
        Export gate: {drcGateMessage} Dry-run and Write to Board stay disabled until the current layout is clean or the override is acknowledged.
      </div>
    {:else}
      <div
        class="rounded-md border border-emerald-500/50 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200"
        role="status"
        aria-live="polite"
      >
        Export gate: {drcGateMessage}
      </div>
    {/if}
  </div>

  <!-- Write / dry-run action buttons -->
  <div class="flex flex-wrap items-center gap-2">
    <button
      type="button"
      onclick={onWrite}
      disabled={writing || (!dryRun && !connected) || (!overrideDrc && drcGateBlocked)}
      class="rounded-md border border-emerald-500/50 bg-emerald-600/30 px-3 py-1.5 text-xs font-medium text-emerald-100 transition hover:bg-emerald-500/40 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {#if writing}
        {dryRun ? "Generating…" : "Writing…"}
      {:else}
        {dryRun ? "Dry Run: Generate Coils" : "Write to Board"}
      {/if}
    </button>

    <!-- Dry run toggle -->
    <label class="ml-auto flex cursor-pointer select-none items-center gap-2 text-xs text-slate-300">
      <input
        type="checkbox"
        checked={dryRun}
        onchange={onToggleDryRun}
        class="h-3.5 w-3.5 rounded border-slate-600 bg-slate-900 accent-sky-500"
      />
      Dry Run
    </label>
  </div>

  <!-- Success toast -->
  {#if toast}
    <div
      class="rounded-md border border-emerald-500/50 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200"
      role="status"
      aria-live="polite"
    >
      {toast}
    </div>
  {/if}

  <!-- Dry-run preview (persistent, separate from transient toast) -->
  {#if dryRunPreview}
    <div
      class="rounded-md border border-sky-500/40 bg-sky-500/5 px-3 py-2 text-xs text-sky-200"
      role="status"
      aria-live="polite"
    >
      {dryRunPreview}
    </div>
  {/if}

  <!-- Last write result summary -->
  {#if writeResult && !zeroItemWrite}
    <div class="text-xs text-slate-400 font-mono">
      Last write: {writeResult.items_created} of {writeResult.items_attempted} item(s)
      {#if writeResult.commit_id}· commit {writeResult.commit_id}{/if}
    </div>
  {/if}

  <!-- Partial-write warning (KiCad rejected some items) -->
  {#if writeResult && writeResult.items_created > 0 && writeResult.items_created < writeResult.items_attempted}
    <div
      class="rounded-md border border-amber-500/60 bg-amber-500/10 px-3 py-2 text-xs text-amber-200"
    >
      <div class="font-semibold">
        Warning: {writeResult.items_attempted - writeResult.items_created} of
        {writeResult.items_attempted} item(s) were rejected by KiCad.
      </div>
      {#if writeResult.failures.length > 0}
        <ul class="mt-1 list-disc pl-5 font-mono text-[11px] leading-snug">
          {#each writeResult.failures as msg (msg)}
            <li>{msg}</li>
          {/each}
        </ul>
        {#if writeResult.failures.length < (writeResult.items_attempted - writeResult.items_created)}
          <div class="mt-1 italic text-amber-300/80">
            (showing first {writeResult.failures.length} of
            {writeResult.items_attempted - writeResult.items_created} failures — open
            dev tools console for the full response.)
          </div>
        {/if}
      {/if}
    </div>
  {/if}
</div>