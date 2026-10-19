<script lang="ts">
  import { render } from "katex";
  import "katex/dist/katex.min.css";

  let { tex, display = false }: { tex: string; display?: boolean } = $props();
</script>

<!-- KaTeX owns the contents; MathML supplies the accessible equation. -->
<span class={['formula', { display }]} {@attach (node) => {
  render(tex, node, { displayMode: display, throwOnError: false, trust: false, output: "htmlAndMathml" });
}}></span>

<style>
  .formula { font-size: 0.95em; }
  .display { display: block; overflow-x: auto; padding-block: 0.25rem; }
  .formula :global(.katex-display) { margin: 0.25rem 0; }
</style>
