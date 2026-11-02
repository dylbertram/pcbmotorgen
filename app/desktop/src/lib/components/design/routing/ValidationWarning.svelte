<script lang="ts">
  import type { ConfigStore } from "../../../stores/config.svelte";
  import { validateDesign, hasErrors as hasFindingsErrors } from "../../../constraints/validation";

  let { config }: { config: ConfigStore } = $props();

  let findings = $derived(validateDesign(config));
  let hasErrors = $derived(hasFindingsErrors(findings));
</script>

{#if findings.length > 0}
  <div
    class={hasErrors
      ? "space-y-2 rounded-md border border-rose-500/60 bg-rose-500/10 px-4 py-3 text-sm text-rose-200"
      : "space-y-2 rounded-md border border-amber-500/60 bg-amber-500/10 px-4 py-3 text-sm text-amber-200"}
    role={hasErrors ? "alert" : "status"}
    aria-live={hasErrors ? "assertive" : "polite"}
  >
    <p class="font-semibold">
      {hasErrors ? "Design needs attention" : "Design guidance"}
    </p>
    {#each findings as finding (finding.id)}
      <p>
        <span class="mr-1 text-[10px] font-semibold uppercase tracking-wider opacity-80">
          {finding.level}
        </span>
        {finding.message}
      </p>
    {/each}
  </div>
{/if}
