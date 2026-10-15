<script lang="ts">
  import WindingConnectionDiagram from "./WindingConnectionDiagram.svelte";
</script>

<div class="wc-help">
  <p class="wc-help-lead">How the three windings are joined.</p>

  <div class="wc-help-figure">
    <span class="wc-help-tag">Delta</span>
    <WindingConnectionDiagram kind="delta" />
  </div>
  <p>The windings join end to end in a ring. Each joint takes one lead.</p>

  <div class="wc-help-figure">
    <span class="wc-help-tag">Star (wye)</span>
    <WindingConnectionDiagram kind="star" />
  </div>
  <p>One end of each winding meets at a neutral. The free ends take the leads.</p>
</div>

<style>
  .wc-help {
    display: grid;
    gap: 4px;
    min-width: 178px;
    font-size: 10px;
    line-height: 1.5;
  }
  .wc-help-lead {
    color: var(--color-slate-300);
    margin-bottom: 2px;
  }
  .wc-help-figure {
    margin-top: 6px;
  }
  .wc-help-tag {
    display: block;
    font-size: 9px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--color-slate-400);
    margin-bottom: 1px;
  }
  p {
    color: var(--color-slate-300);
    margin: 1px 0 0;
  }
</style>
