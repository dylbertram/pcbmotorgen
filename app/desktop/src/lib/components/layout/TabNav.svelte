<script lang="ts">
  import { Tabs } from "bits-ui";
  import type { TabId } from "../../ui";

  let {
    tabs,
    statusFor,
  }: {
    tabs: { id: TabId; label: string }[];
    statusFor: (tab: TabId) => { label: string; className: string };
  } = $props();
</script>

<!--
  Zone 2 of the slim top bar: browser-style file tabs attached to the
  header's bottom divider. The active tab shares the page background and
  overlaps the divider by 1px (-mb-px), so it reads as "open" onto the
  content below. Bits UI's Tabs primitive provides roving-focus keyboard
  navigation (arrow/Home/End) with automatic activation; tab selection
  itself is owned by the Tabs.Root in App.svelte.
-->
<nav aria-label="Design workflows" class="px-3">
  <Tabs.List
    class="flex items-end gap-1 border-b border-slate-800"
    aria-label="Design workflow tabs"
  >
    {#each tabs as tab (tab.id)}
      {@const status = statusFor(tab.id)}
      <Tabs.Trigger
        value={tab.id}
        id={`tab-${tab.id}`}
        class="-mb-px rounded-t-md border border-b-0 px-3.5 py-1.5 text-sm transition-colors
          data-[state=active]:border-slate-800 data-[state=active]:bg-slate-900 data-[state=active]:font-semibold data-[state=active]:text-slate-100
          data-[state=inactive]:border-transparent data-[state=inactive]:text-slate-400 data-[state=inactive]:hover:bg-slate-800/60 data-[state=inactive]:hover:text-slate-200"
      >
        {tab.label}
        <span class={`ml-2 text-[10px] font-normal uppercase tracking-wider ${status.className}`}>
          {status.label}
        </span>
      </Tabs.Trigger>
    {/each}
  </Tabs.List>
</nav>
