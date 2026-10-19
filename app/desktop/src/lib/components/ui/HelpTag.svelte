<script lang="ts">
  import { Tooltip } from "bits-ui";
  import type { Snippet } from "svelte";
  import Formula from "./Formula.svelte";

  /**
   * Hoverable/focusable info superscript tag built on Bits UI's accessible
   * Tooltip primitive (floating-UI positioning with collision handling, so
   * overflow-hidden panel containers can never clip it). Shows `tip` text
   * — or a rich `children` snippet (e.g. mathematical symbols with
   * sub/superscripts) — plus an optional `image` (imported asset URL,
   * e.g. an inline SVG illustration).
   */
  interface HelpTagProps {
    /** Plain-text tooltip body; ignored when a `children` snippet is passed. */
    tip?: string;
    image?: string;
    imageAlt?: string;
    label?: string;
    equation?: string;
    /** Rich tooltip body, e.g. symbols like τ<sub>p</sub>. */
    children?: Snippet;
  }

  let {
    tip,
    image,
    imageAlt = "",
    label = "More information",
    children,
    equation,
  }: HelpTagProps = $props();
  let open = $state(false);
</script>

<Tooltip.Provider delayDuration={150}>
  <Tooltip.Root bind:open disableCloseOnTriggerClick>
    <Tooltip.Trigger
      class="relative ml-1 inline-flex shrink-0 cursor-help items-center justify-center rounded-sm text-slate-400 transition-colors hover:text-emerald-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-400"
      aria-label={label}
      onclick={() => (open = true)}
    >
      <svg
        viewBox="0 0 12 12"
        class="inline-block h-3 w-3"
        fill="none"
        stroke="currentColor"
        stroke-width="1.3"
        aria-hidden="true"
      >
        <circle cx="6" cy="6" r="5.2" />
        <line x1="6" y1="5.4" x2="6" y2="8.8" stroke-linecap="round" />
        <circle cx="6" cy="3.3" r="0.55" fill="currentColor" stroke="none" />
      </svg>
    </Tooltip.Trigger>
    <Tooltip.Portal>
      <Tooltip.Content
        role="tooltip"
        side="top"
        sideOffset={6}
        collisionPadding={8}
        class="z-[100] w-72 max-w-[calc(100vw-1rem)] rounded-md border border-slate-600 bg-slate-900 px-3 py-2.5 text-left text-xs font-normal leading-relaxed text-slate-200 shadow-lg shadow-black/40"
      >
        {#if children}
          {@render children()}
        {:else if tip}
          {tip}
        {/if}
        {#if equation}<Formula tex={equation} display />{/if}
        {#if image}
          <img
            src={image}
            alt={imageAlt}
            draggable="false"
            class="mt-1.5 w-full"
          />
        {/if}
      </Tooltip.Content>
    </Tooltip.Portal>
  </Tooltip.Root>
</Tooltip.Provider>
