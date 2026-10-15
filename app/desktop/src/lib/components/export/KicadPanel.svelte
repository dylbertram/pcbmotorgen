<script lang="ts">
  import {
    connectKicad,
    writeCoilsToBoard,
    getBoardDiagnostics,
    validateWritePreconditions,
    previewCoils,
  } from "../../ipc";
  import type { ConfigStore } from "../../stores/config.svelte";
  import type {
    KicadConnection,
    KicadWriteResult,
    BoardDiagnostics,
    PreconditionWarning,
    CoilPreview,
    InterferenceViolation,
    CadGeometry,
  } from "../../types";
  import { unmappedCoils } from "../../cadPhases";
  import KicadConnectionCard from "./KicadConnectionCard.svelte";
  import KicadPreflightCard from "./KicadPreflightCard.svelte";
  import KicadWriteControls from "./KicadWriteControls.svelte";

  let {
    config,
    drcViolations,
    drcLoading,
    drcError,
    drcReady,
    drcLayoutKey,
    cadGeometry = null,
  }: {
    config: ConfigStore;
    /** Imported copper to write instead of the generated coils. */
    cadGeometry?: CadGeometry | null;
    drcViolations: InterferenceViolation[];
    drcLoading: boolean;
    drcError: string | null;
    drcReady: boolean;
    drcLayoutKey: string;
  } = $props();

  // --- State -------------------------------------------------------------
  let connection = $state<KicadConnection | null>(null);
  let diagnostics = $state<BoardDiagnostics | null>(null);
  let connecting = $state(false);
  let refreshingDiag = $state(false);
  let validating = $state(false);
  let previewing = $state(false);
  let writing = $state(false);
  let dryRun = $state(false);
  let error = $state<string | null>(null);
  let writeResult = $state<KicadWriteResult | null>(null);
  let validationWarnings = $state<PreconditionWarning[] | null>(null);
  let previewResult = $state<CoilPreview | null>(null);
  let toast = $state<string | null>(null);
  let dryRunPreview = $state<string | null>(null);
  let acknowledgedDrcLayoutKey = $state<string | null>(null);

  // Timeout handle for the auto-dismissing success toast.
  let toastTimer: ReturnType<typeof setTimeout> | undefined;

  // --- Derived -----------------------------------------------------------
  let unmapped = $derived(cadGeometry ? unmappedCoils(cadGeometry) : []);
  let connected = $derived(connection?.connected ?? false);
  let boardName = $derived(connection?.board_name ?? "(not connected)");
  let copperLayers = $derived(connection?.copper_layers ?? 0);
  let drcViolationCount = $derived(drcViolations.length);
  let drcGateBlocked = $derived(!drcReady || drcViolationCount > 0);
  let drcGateMessage = $derived.by(() => {
    if (drcLoading) return "DRC is checking the current layout.";
    if (drcError) return `DRC could not complete: ${drcError}`;
    if (!drcReady) return "DRC has not completed for the current layout.";
    if (drcViolationCount > 0) {
      return `${drcViolationCount} DRC violation${drcViolationCount === 1 ? "" : "s"} block export.`;
    }
    return "DRC complete: the current layout is clear.";
  });

  // Acknowledgement is session-local and tied to the current layout identity,
  // so it cannot silently carry across a different design.
  let overrideDrc = $derived(acknowledgedDrcLayoutKey === drcLayoutKey);

  function handleDrcOverrideChange(event: Event): void {
    const checked = (event.currentTarget as HTMLInputElement).checked;
    acknowledgedDrcLayoutKey = checked ? drcLayoutKey : null;
  }

  function handleToggleDryRun(event: Event): void {
    dryRun = (event.currentTarget as HTMLInputElement).checked;
  }

  /**
   * True when the most recent write attempted to create 0 items — i.e.
   * the historical "0 of 0 written" bug. We use this to swap the
   * "Wrote 0 of 0" toast (which looks like success) for a clear error
   * message, since the underlying issue is "the coil generator produced
   * no coils" — the user needs to know that, not see a green checkmark.
   */
  let zeroItemWrite = $derived(
    writeResult !== null &&
      writeResult.items_attempted === 0 &&
      writeResult.items_created === 0,
  );

  /** Flash a transient success/info message that auto-clears after 4s. */
  function showToast(msg: string): void {
    if (toastTimer) clearTimeout(toastTimer);
    toast = msg;
    toastTimer = setTimeout(() => {
      toast = null;
      toastTimer = undefined;
    }, 4000);
  }

  // --- Handlers ----------------------------------------------------------
  async function handleConnect(): Promise<void> {
    connecting = true;
    error = null;
    writeResult = null;
    dryRunPreview = null;
    try {
      connection = await connectKicad();
      if (!connection.connected) {
        error = "KiCad IPC socket unavailable — running in mock mode.";
      }
    } catch (e) {
      connection = null;
      error = e instanceof Error ? e.message : String(e);
    } finally {
      connecting = false;
    }
  }

  async function handleRefreshDiagnostics(): Promise<void> {
    refreshingDiag = true;
    error = null;
    try {
      diagnostics = await getBoardDiagnostics();
    } catch (e) {
      diagnostics = null;
      error = e instanceof Error ? e.message : String(e);
    } finally {
      refreshingDiag = false;
    }
  }

  async function handleValidate(): Promise<void> {
    validating = true;
    error = null;
    try {
      // Lazy-fetch diagnostics if the user hasn't called
      // handleRefreshDiagnostics() first. validateWritePreconditions
      // needs the live board snapshot.
      if (!diagnostics) diagnostics = await getBoardDiagnostics();
      const ipc = config.toIpc();
      validationWarnings = await validateWritePreconditions(ipc, diagnostics, cadGeometry);
      const n = validationWarnings.length;
      const errs = validationWarnings.filter((w) => w.level === "error").length;
      const tail = n === 0
        ? "no issues — safe to write."
        : `${n} finding(s) (${errs} blocking)`;
      showToast(`Validation complete: ${tail}`);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      validating = false;
    }
  }

  async function handlePreview(): Promise<void> {
    previewing = true;
    error = null;
    try {
      const ipc = config.toIpc();
      previewResult = await previewCoils(ipc, cadGeometry);
      showToast(
        `Preview: ${previewResult.num_layers} layer(s), ` +
          `${previewResult.total_tracks} track(s), ` +
          `${previewResult.total_vias} via(s).`,
      );
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      previewing = false;
    }
  }

  async function handleWrite(): Promise<void> {
    if (unmapped.length) {
      error = `Assign a phase to every imported coil before writing (unassigned: ${unmapped.join(", ")}).`;
      return;
    }
    if (!overrideDrc && drcGateBlocked) {
      error = `Export blocked: ${drcGateMessage} Acknowledge the DRC override to continue.`;
      return;
    }
    if (!connected && !dryRun) return;
    writing = true;
    error = null;
    writeResult = null;
    dryRunPreview = null;
    try {
      const ipc = config.toIpc();
      const result = await writeCoilsToBoard(ipc, dryRun, cadGeometry);
      writeResult = result;

      // Special-case the "0 of 0" bug: don't show a green toast when
      // nothing was actually written. The Rust side logs the per-layer
      // breakdown to stderr ([pcbmotorgen::write_coils]) — the user
      // can open dev tools to see the diagnostic line.
      if (zeroItemWrite) {
        error =
          `No items were generated by the coil writer (0 attempted, ` +
          `0 created). Check your config — phases, active_area_length, ` +
          `and num_layers must be non-zero. See dev tools for the ` +
          `[pcbmotorgen::write_coils] diagnostic line.`;
        // No toast — the error banner is the right channel.
        return;
      }

      const partial = result.items_created < result.items_attempted;
      const tail = partial
        ? ` of ${result.items_attempted} (${result.items_attempted - result.items_created} failed)`
        : ` of ${result.items_attempted}`;
      if (dryRun) {
        const msg = `Dry run: would write ${result.items_created}${tail} item(s). ${result.commit_id}`;
        dryRunPreview = msg;
        showToast(msg);
      } else {
        const commit = result.commit_id ? ` (commit ${result.commit_id})` : "";
        showToast(
          `Wrote ${result.items_created}${tail} item(s) to board${commit}.`,
        );
      }
    } catch (e) {
      // Real Tauri error — surface to the UI. This is the fix for the
      // "0 of 0" bug: a backend failure no longer gets hidden behind a
      // synthetic zero-result.
      error = e instanceof Error ? e.message : String(e);
    } finally {
      writing = false;
    }
  }
</script>

<div class="rounded-lg bg-slate-800/40 border border-slate-700 p-4 space-y-3">
  <div class="flex items-center justify-between">
    <h3 class="text-sm font-semibold text-slate-200 border-b border-slate-700 pb-1 flex-1">
      KiCad Board Writer
    </h3>
    <!-- Connection status dot -->
    <div class="flex items-center gap-2 text-xs ml-3">
      <span
        class="inline-block h-3 w-3 rounded-full {connected
          ? 'bg-emerald-400'
          : 'bg-rose-500'}"
      ></span>
      <span class={connected ? "text-emerald-300" : "text-rose-300"}>
        {connected ? "connected" : "disconnected"}
      </span>
    </div>
  </div>

  <KicadConnectionCard
    {connection}
    {connected}
    {boardName}
    {copperLayers}
    {diagnostics}
    {connecting}
    {refreshingDiag}
    onConnect={handleConnect}
    onRefresh={handleRefreshDiagnostics}
  />

  <KicadPreflightCard
    {validationWarnings}
    {validating}
    {previewResult}
    {previewing}
    onValidate={handleValidate}
    onPreview={handlePreview}
  />

  <KicadWriteControls
    {dryRun}
    {writing}
    {connected}
    {writeResult}
    {drcReady}
    {drcError}
    {overrideDrc}
    {zeroItemWrite}
    {toast}
    {dryRunPreview}
    {drcViolationCount}
    {drcGateBlocked}
    {drcGateMessage}
    onToggleDryRun={handleToggleDryRun}
    onDrcOverrideChange={handleDrcOverrideChange}
    onWrite={handleWrite}
  />

  <!-- Error banner -->
  {#if error}
    <div
      class="rounded-md border border-rose-500/60 bg-rose-500/10 px-3 py-2 text-xs text-rose-200"
      role="alert"
      aria-live="assertive"
    >
      <span class="font-semibold">Error:</span> {error}
    </div>
  {/if}
</div>