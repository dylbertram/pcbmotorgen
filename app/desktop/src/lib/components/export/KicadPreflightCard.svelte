<script lang="ts">
  import { warningClasses, warningLabel } from "./preflightWarning";
  import type { PreconditionWarning, CoilPreview } from "../../types";

  let {
    validationWarnings,
    validating,
    previewResult,
    previewing,
    onValidate,
    onPreview,
  }: {
    validationWarnings: PreconditionWarning[] | null;
    validating: boolean;
    previewResult: CoilPreview | null;
    previewing: boolean;
    onValidate: () => void;
    onPreview: () => void;
  } = $props();
</script>

<div class="space-y-3">
  <!-- Validation warnings (from validate_write_preconditions) -->
  {#if validationWarnings && validationWarnings.length > 0}
    <div class="space-y-1">
      <div class="text-xs font-semibold text-slate-300">Pre-flight checks</div>
      {#each validationWarnings as w (`${w.level}:${w.field ?? ""}:${w.message}`)}
        <div
          class="rounded-md border px-3 py-2 text-xs {warningClasses(w.level)}"
        >
          <span class="font-mono text-[10px] font-semibold mr-2">
            [{warningLabel(w.level)}{w.field ? ` · ${w.field}` : ""}]
          </span>
          {w.message}
        </div>
      {/each}
    </div>
  {:else if validationWarnings && validationWarnings.length === 0}
    <div
      class="rounded-md border border-emerald-500/50 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200"
    >
      Pre-flight: no issues — config is compatible with the open board.
    </div>
  {/if}

  <!-- Coil preview summary (from preview_coils) -->
  {#if previewResult}
    <div
      class="rounded-md border border-sky-500/40 bg-sky-500/5 px-3 py-2 text-xs text-sky-200"
    >
      <div class="font-semibold mb-1">Coil preview ({previewResult.pattern_id})</div>
      <div class="font-mono text-[11px] leading-snug">
        {previewResult.num_layers} layer(s) ·
        {previewResult.total_tracks} track(s) ·
        {previewResult.total_vias} via(s)
      </div>
      <ul class="mt-1 list-disc pl-5 font-mono text-[11px] leading-snug">
        {#each previewResult.layers as layer (layer.layer_idx)}
          <li>
            layer {layer.layer_idx}: {layer.phase_count} phase(s),
            {layer.segment_count} segment(s),
            {layer.via_count} via(s)
          </li>
        {/each}
      </ul>
    </div>
  {/if}

  <!-- Pre-flight action buttons -->
  <div class="flex flex-wrap items-center gap-2">
    <button
      type="button"
      onclick={onValidate}
      disabled={validating}
      class="rounded-md border border-amber-500/50 bg-amber-600/30 px-3 py-1.5 text-xs font-medium text-amber-100 transition hover:bg-amber-500/40 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {validating ? "Validating…" : "Validate"}
    </button>

    <button
      type="button"
      onclick={onPreview}
      disabled={previewing}
      class="rounded-md border border-sky-500/50 bg-sky-600/30 px-3 py-1.5 text-xs font-medium text-sky-100 transition hover:bg-sky-500/40 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {previewing ? "Previewing…" : "Preview"}
    </button>
  </div>
</div>
