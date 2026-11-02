<script lang="ts">
  import { Separator } from "bits-ui";

  /**
   * Decorative horizontal divider, hidden from the accessibility tree.
   */
  interface SeparatorProps {
    /** Color/spacing utilities; the sizing defaults below stay. */
    class?: string; // default "bg-slate-700"
  }

  let {
    class: cls = "bg-slate-700",
  }: SeparatorProps = $props();
</script>

<Separator.Root
  orientation="horizontal"
  decorative
  class="h-px w-full {cls}"
/>
