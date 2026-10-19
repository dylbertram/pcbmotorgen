<script lang="ts">
  import WindingConnectionDiagram from "./WindingConnectionDiagram.svelte";
</script>

<div class="wc-help">
  <div class="wc-help-figure">
    <span class="wc-help-tag">Delta</span>
    <WindingConnectionDiagram kind="delta" />
  </div>
  <p>Windings form a ring. Each joint connects to the driver.</p>

  <div class="wc-help-figure">
    <span class="wc-help-tag">Star (wye)</span>
    <WindingConnectionDiagram kind="star" />
  </div>
  <p>Windings share a neutral. The free ends connect to the driver.</p>
</div>

<style>
  .wc-help {
    display: grid;
    gap: 4px;
    min-width: 178px;
    font-size: 12px;
    line-height: 1.5;
  }
  .wc-help-figure {
    margin-top: 6px;
  }
  .wc-help-tag {
    display: block;
    font-size: 12px;
    font-weight: 600;
    color: rgb(var(--slate-200));
    margin-bottom: 1px;
  }
  p {
    color: rgb(var(--slate-300));
    margin: 1px 0 0;
  }
</style>
