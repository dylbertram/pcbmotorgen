<script lang="ts">
  import type { Snippet } from "svelte";
  import HelpTag from "../ui/HelpTag.svelte";

  let { label, help, children }: { label: string; help?: string; children: Snippet } = $props();
</script>

<div class="flex min-w-0 items-center justify-between gap-2">
  <span class="flex min-w-0 items-center gap-1 truncate text-xs text-slate-300">
    {label}
    {#if help}<HelpTag tip={help} />{/if}
  </span>
  {@render children()}
</div>
