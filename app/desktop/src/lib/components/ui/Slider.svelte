<script lang="ts">
  import { Slider } from "bits-ui";

  /**
   * Single-value slider built on Bits UI's accessible Slider primitive:
   * the thumb carries `role="slider"` with native Arrow/Home/End keyboard
   * support, and pointer dragging writes continuously through
   * `onValueChange`. Dark-slate track with an emerald range/thumb matching
   * the app accent. Wrapper conventions follow NumberField.svelte.
   */
  interface SliderProps {
    /** Lowest selectable value. */
    min?: number; // default 0
    /** Highest selectable value. */
    max?: number; // default 100
    /** Granularity of the value. */
    step?: number; // default 1
    /** Controlled value; two-way bindable (e.g. `bind:value={getter, setter}`). */
    value?: number;
    disabled?: boolean;
    /** Accessible name for the slider thumb (role="slider"). */
    ariaLabel: string;
    /** Root classes appended after the base root classes. */
    class?: string;
    /** Fires for every value the primitive writes (drag/keyboard). */
    onValueChange?: (value: number) => void;
    /** Fires when a value interaction ends (commit). */
    onValueCommit?: (value: number) => void;
  }

  let {
    min = 0,
    max = 100,
    step = 1,
    value = $bindable(),
    disabled = false,
    ariaLabel,
    class: rootClass = "",
    onValueChange,
    onValueCommit,
  }: SliderProps = $props();
</script>

<Slider.Root
  type="single"
  {min}
  {max}
  {step}
  bind:value
  {disabled}
  {onValueChange}
  {onValueCommit}
  class="relative flex w-full touch-none select-none items-center {rootClass}"
>
  <!-- bits-ui 2.x exposes no Track part; the Range positions itself inside
       this plain relative span (shadcn-svelte pattern). -->
  <span class="relative h-1 w-full grow overflow-hidden rounded-full bg-slate-700">
    <Slider.Range class="absolute h-full bg-emerald-500" />
  </span>
  <Slider.Thumb
    index={0}
    aria-label={ariaLabel}
    class="block size-3.5 shrink-0 cursor-pointer rounded-full border border-emerald-200 bg-emerald-400 shadow transition-shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60 disabled:cursor-not-allowed disabled:opacity-50"
  />
</Slider.Root>
