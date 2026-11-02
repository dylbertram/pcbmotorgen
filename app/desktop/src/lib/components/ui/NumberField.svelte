<script lang="ts">
  import { isMultipleOf } from "../../constraints/layerConstraints";

  /**
   * A numeric text field that keeps the last committed value in the parent
   * store while the user is editing. Invalid drafts stay local to this
   * component, so an empty string, NaN, an out-of-range value, or an
   * off-multiple value (when `multipleOf` is set) can never reach
   * ConfigStore.
   */
  interface NumberFieldProps {
    value: number;
    min?: number;
    max?: number;
    step?: number;
    integer?: boolean;
    /** Valid values are multiples of this (epsilon-tolerant, mirroring the
     *  routing crate's 1e-9 discipline). An off-multiple draft stays local
     *  and is shown as invalid — it can never be committed. */
    multipleOf?: number;
    id?: string;
    ariaLabel?: string;
    describedBy?: string;
    disabled?: boolean;
    class?: string;
    onCommit: (value: number) => void;
  }

  const generatedId = $props.id();

  let {
    value,
    min,
    max,
    step,
    integer = false,
    multipleOf,
    id,
    ariaLabel,
    describedBy,
    disabled = false,
    class: inputClass = "",
    onCommit,
  }: NumberFieldProps = $props();

  let inputId = $derived(id ?? generatedId);
  let errorId = $derived(`${inputId}-error`);

  let draftOverride = $state<string | null>(null);
  let error = $state<string | null>(null);
  let draft = $derived(draftOverride ?? formatValue(value));

  function formatValue(valueToFormat: number): string {
    return Number.isFinite(valueToFormat) ? String(valueToFormat) : "";
  }

  function validate(raw: string): { value: number | null; error: string | null } {
    if (raw.trim() === "") {
      return { value: null, error: "Enter a number." };
    }

    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) {
      return { value: null, error: "Enter a finite number." };
    }
    if (integer && !Number.isInteger(parsed)) {
      return { value: null, error: "Value must be a whole number." };
    }
    if (min !== undefined && Number.isFinite(min) && parsed < min) {
      return { value: null, error: `Value must be at least ${min}.` };
    }
    if (max !== undefined && Number.isFinite(max) && parsed > max) {
      return { value: null, error: `Value must be at most ${max}.` };
    }
    if (multipleOf !== undefined && !isMultipleOf(parsed, multipleOf)) {
      return {
        value: null,
        error: `Value must be a multiple of ${multipleOf}.`,
      };
    }

    return { value: parsed, error: null };
  }

  function handleInput(event: Event): void {
    const raw = (event.currentTarget as HTMLInputElement).value;
    draftOverride = raw;

    const result = validate(raw);
    error = result.error;
    if (result.value === null) return;

    onCommit(result.value);
  }

  function handleBlur(): void {
    // An invalid draft never touched the store. Restore the current store
    // value when editing ends; while focused, the red error state remains
    // visible so the user can correct it without losing the last valid value.
    draftOverride = null;
    error = null;
  }

  let describedByValue = $derived(
    error ? errorId : describedBy,
  );

  let inputClasses = $derived(
    [
      "rounded-md border px-3 py-1.5 text-sm focus:outline-none",
      error
        ? "border-rose-500 bg-rose-500/10 text-rose-100 focus:border-rose-400"
        : "border-slate-700 bg-slate-800 text-slate-100 focus:border-emerald-500",
      inputClass,
      disabled ? "cursor-not-allowed opacity-60" : "",
    ]
      .filter(Boolean)
      .join(" "),
  );
</script>

<span class="block min-w-0">
  <input
    id={inputId}
    type="number"
    value={draft}
    min={min}
    max={max}
    step={step}
    aria-label={ariaLabel}
    aria-invalid={error !== null}
    aria-describedby={describedByValue}
    disabled={disabled}
    class={inputClasses}
    oninput={handleInput}
    onblur={handleBlur}
  />
  {#if error}
    <span id={errorId} class="mt-1 block text-xs text-rose-300" role="alert" aria-live="polite">
      {error}
    </span>
  {/if}
</span>
