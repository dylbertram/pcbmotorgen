<script lang="ts">
  import HelpTag from "../ui/HelpTag.svelte";
  import type { Snippet } from "svelte";

  let { holeMm, ringMm, children }: { holeMm: number; ringMm: number; children?: Snippet } = $props();
  let diameterMm = $derived(holeMm + 2 * ringMm);
  let holeRadius = $derived(diameterMm > 0 ? 34 * Math.max(0, holeMm) / diameterMm : 0);
  const mm = (value: number) => `${value.toFixed(3)} mm`;
</script>

<figure class="via-guide" aria-label="Via sizing guide">
  <figcaption>
    {#if children}<div class="via-inputs">{@render children()}</div>{/if}
    <dl>
      <div><dt>Via diameter<HelpTag
        label="About via diameter"
        tip="Outer copper diameter. The ring surrounds both sides of the drilled hole."
        equation={String.raw`D_{\mathrm{via}} = D_{\mathrm{hole}} + 2w_{\mathrm{ring}}`}
      /></dt><dd>{mm(diameterMm)}</dd></div>
    </dl>
  </figcaption>
  <svg viewBox="0 0 140 132" role="img" aria-label="Via viewed from above. The hole is inside a copper ring. Hole size and via diameter span the full circle; ring width is measured on one side.">
    <circle cx="70" cy="57" r="34" class="copper" />
    <circle cx="70" cy="57" r={holeRadius} class="hole" />
    <g class="dimensions" fill="none" stroke-width="1">
      <path d="M36 94v16m68-16v16M36 104h68m-68-3 3 3-3 3m68-6-3 3 3 3" />
      <path d="M36 54v6m68-6v6" />
      <path d="M{70 - holeRadius} 57H{70 + holeRadius}m{-2 * holeRadius} -3v6m{2 * holeRadius} -6v6" />
      <path d="M{70 + holeRadius} 57V26M104 57V26M{70 + holeRadius} 30H104" />
    </g>
    <g class="diagram-labels" text-anchor="middle">
      <text x="70" y="121">Via diameter</text>
      <text x="70" y="52">Hole</text>
      <text x="96" y="19">Ring width</text>
    </g>
  </svg>
</figure>

<style>
  .via-guide { display: grid; grid-template-columns: minmax(0, 1fr) 7rem; gap: 0.5rem 1rem; align-items: center; width: 100%; margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid rgb(var(--slate-700)); }
  svg { display: block; width: 100%; grid-column: 2; grid-row: 1; }
  figcaption { grid-column: 1; grid-row: 1; min-width: 0; }
  .via-inputs { display: grid; gap: 0.625rem; margin-bottom: 0.625rem; }
  .copper { fill: #fbbf24; stroke: #b45309; stroke-width: 1; }
  .hole { fill: rgb(var(--slate-900)); stroke: rgb(var(--slate-500)); stroke-width: 1; }
  .dimensions { stroke: rgb(var(--slate-300)); }
  .diagram-labels { fill: rgb(var(--slate-300)); font: 10px sans-serif; }
  dl { display: grid; gap: 0.35rem; font-size: 0.75rem; }
  dl div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 0.25rem 0.75rem; }
  dt { color: rgb(var(--slate-300)); }
  dd { color: rgb(var(--slate-200)); font-variant-numeric: tabular-nums; }
  @media (max-width: 480px) {
    .via-guide { grid-template-columns: minmax(0, 1fr) 6rem; }
    .via-inputs :global(label) { flex-wrap: wrap; }
    .via-inputs :global(label > span:first-child) { flex-basis: 100%; }
  }
</style>
