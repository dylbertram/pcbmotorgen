<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { BackplaneAnalysis, DriveBackplane, CadGeometry, RoutingDimensionsDto } from "../../types";
  import BackplanePanel from "./stackup/BackplanePanel.svelte";
  import MagnetsPanel from "./magnets/MagnetsPanel.svelte";
  import DrivePanel from "./drive/DrivePanel.svelte";
  import type { MotionStore } from "../../stores/motion.svelte";
  import type { TraceMeasure } from "../../preview/previewGeometry";
  import DesignConstraints from "./routing/DesignConstraints.svelte";
  import RoutingSourcePanel from "./routing/RoutingSourcePanel.svelte";
  import TracesBoardPanel from "./routing/TracesBoardPanel.svelte";
  import RoutingOrientationPanel from "./routing/RoutingOrientationPanel.svelte";
  import ScrollArea from "../ui/ScrollArea.svelte";
  import type { DesignPanelId } from "../../preview/previewPanels";

  let {
    config,
    motion,
    measuredTrace = null,
    routingDimensions = null,
    cadGeometry = null,
    onImportCad,
    onUseGenerated,
    onGeometryChange,
    backplaneAnalysis = null,
    driveBackplane = null,
    section = "routing",
  }: {
    config: ConfigStore;
    motion: MotionStore;
    measuredTrace?: TraceMeasure | null;
    routingDimensions?: RoutingDimensionsDto | null;
    cadGeometry?: CadGeometry | null;
    onImportCad: () => void;
    onUseGenerated: () => void;
    onGeometryChange?: (geometry: CadGeometry) => void;
    backplaneAnalysis?: BackplaneAnalysis | null;
    driveBackplane?: DriveBackplane | null;
    section?: DesignPanelId;
  } = $props();
</script>

<ScrollArea
  id="design-settings-scroll"
  class="h-full"
  viewportClass="p-3"
  aria-label={`${section} settings`}
>
  <div class="design-settings space-y-3">
    {#if section === "stackup"}

    <BackplanePanel {config} {backplaneAnalysis} {driveBackplane} {cadGeometry} />
    {:else if section === "routing"}

    <!-- Topology (routing pattern + parameters + generator load) and the
         board/winding fields share one panel so winding geometry can be
         reviewed and edited side by side. -->
    <section
      id="topology-board-heading"
      aria-label="Routing"
    >
      <div class="space-y-3">
        <RoutingSourcePanel {config} cadGeometryActive={cadGeometry !== null} cadSourceFileName={cadGeometry?.source_file_name} {onImportCad} {onUseGenerated} />
        <RoutingOrientationPanel {config} geometry={cadGeometry} {onGeometryChange} />
        <DesignConstraints {config} {motion} {measuredTrace} {routingDimensions} />
        {#if cadGeometry}
          <div
            class="rounded-md border border-sky-500/30 bg-sky-500/5 px-3 py-3"
            role="group"
            aria-label="Imported CAD pattern"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p class="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  Routing source
                </p>
                <p class="mt-0.5 text-sm font-medium text-sky-200">Imported CAD pattern</p>
              </div>
              <span class="rounded-full border border-sky-400/30 bg-sky-400/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-sky-200">
                Imported
              </span>
            </div>
            <p class="mt-2 text-[11px] leading-relaxed text-slate-400">
               Imported paths are active. Edit trace and via sizes below, or choose a generator to replace them.
            </p>
            <dl class="mt-3 grid grid-cols-3 gap-2 border-t border-slate-700/70 pt-2">
              <div>
                <dt class="text-[10px] text-slate-500">Copper layers</dt>
                <dd class="font-mono text-xs text-slate-200">{cadGeometry.layer_z_mm.length}</dd>
              </div>
              <div>
                <dt class="text-[10px] text-slate-500">Trace elements</dt>
                <dd class="font-mono text-xs text-slate-200">
                  {cadGeometry.routing.segments.length + cadGeometry.routing.curves.length + (cadGeometry.routing.splines?.length ?? 0)}
                </dd>
              </div>
              <div>
                <dt class="text-[10px] text-slate-500">Vias</dt>
                <dd class="font-mono text-xs text-slate-200">{cadGeometry.routing.vias.length}</dd>
              </div>
            </dl>
          </div>
        {/if}
        <TracesBoardPanel {config} traceWidthMm={cadGeometry?.trace_width_mm}
          onTraceWidthChange={cadGeometry && onGeometryChange ? (width) => {
            if (cadGeometry) onGeometryChange?.({ ...cadGeometry, trace_width_mm: width });
           } : undefined} />
      </div>
    </section>

    {:else if section === "magnets"}
      <MagnetsPanel {config} />
    {:else if section === "drive"}
      <DrivePanel {config} />
    {/if}
  </div>
</ScrollArea>

<style>
  .design-settings { container-type: inline-size; }
</style>
