<script lang="ts">
  import { ScrollArea } from "bits-ui";
  import type { ComponentProps, Snippet } from "svelte";

  /**
   * Custom-scrollbar scrolling region built on Bits UI's ScrollArea
   * primitive. Bits hides the native scrollbar; a themed vertical
   * scrollbar (slate thumb) overlays the right edge and appears on hover.
   *
   * Sizing: the Root is a column flex container and the Viewport is
   * `min-h-0 flex-1`, so BOTH definite heights (`h-full`) and capped
   * heights (`max-h-64`) turn the viewport into a real bounded scroll
   * container — a plain block root with a `h-full` viewport would not
   * constrain a `max-h-*` root's content height.
   *
   * All other props (id, aria-label, type, ...) are spread onto
   * ScrollArea.Root.
   */
  interface ScrollAreaProps
    extends Omit<ComponentProps<typeof ScrollArea.Root>, "children" | "child" | "class" | "ref"> {
    /** Root container classes, e.g. "h-full" or "max-h-64". */
    class?: string;
    /** Extra classes for the scrolling viewport. */
    viewportClass?: string;
    /** Vertical scrollbar thumb color override; default "bg-slate-600". */
    scrollbarClass?: string;
    children: Snippet;
  }

  let {
    class: rootClass = "",
    viewportClass = "",
    scrollbarClass = "bg-slate-600",
    children,
    ...rest
  }: ScrollAreaProps = $props();
</script>

<ScrollArea.Root class="relative flex flex-col overflow-hidden {rootClass}" {...rest}>
  <ScrollArea.Viewport class="w-full min-h-0 flex-1 {viewportClass}">
    {@render children()}
  </ScrollArea.Viewport>
  <ScrollArea.Scrollbar
    orientation="vertical"
    class="h-full flex w-2.5 touch-none select-none flex-col justify-center rounded-md bg-transparent p-0.5 transition-colors data-[state=visible]:bg-slate-800/60"
  >
    <ScrollArea.Thumb class="relative rounded-full {scrollbarClass}" />
  </ScrollArea.Scrollbar>
  <ScrollArea.Corner />
</ScrollArea.Root>
