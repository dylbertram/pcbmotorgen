<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { BackplaneAnalysis, DriveBackplane, CadGeometry, RoutingDimensionsDto } from "../../types";
  import BackplanePanel from "../design/BackplanePanel.svelte";
  import MagnetsPanel from "../design/parameters/MagnetsPanel.svelte";
  import DrivePanel from "../design/parameters/DrivePanel.svelte";
  import type { MotionStore } from "../../stores/motion.svelte";
  import { stripBoundsDomainMm, type TraceMeasure } from "../../previewGeometry";
  import TravelIsoView from "../design/TravelIsoView.svelte";
  import ConstraintReadouts from "../design/ConstraintReadouts.svelte";
  import TopologySelector from "../design/TopologySelector.svelte";
  import TracesBoardPanel from "../design/parameters/TracesBoardPanel.svelte";
  import RoutingOrientationPanel from "../design/RoutingOrientationPanel.svelte";
  import ValidationWarning from "../design/ValidationWarning.svelte";
  import NumberField from "../ui/NumberField.svelte";
  import HelpTag from "../ui/HelpTag.svelte";
  import Formula from "../ui/Formula.svelte";
  import ScrollArea from "../ui/ScrollArea.svelte";
  import electricalPitchSvg from "../../assets/electrical-pitch.svg";
  import type { DesignPanelId } from "../design/previewPanels";

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
  const stripBounds = $derived(stripBoundsDomainMm(config, motion));
</script>

<ScrollArea
  id="design-settings-scroll"
  class="h-full"
  viewportClass="p-3"
  aria-label={`${section} settings`}
>
  <div class="design-settings space-y-3">
    <!-- Travel inputs, live assembly geometry and derived sizing readouts. -->
    {#snippet constraints()}
    <section
      id="design-constraints-heading"
      aria-label="Design constraints"
    >
      <div class="grid gap-x-3 gap-y-2.5">
        <label
          class="min-w-0"
        >
          <span class="flex items-center justify-between gap-2">
            <span class="min-w-0 truncate text-xs text-slate-300"
              >Travel (mm)<HelpTag
                label="About desired travel"
                tip="Center-to-center travel. The copper must cover the mover span plus this distance."
                equation={String.raw`L_{\mathrm{active}} = L_{\mathrm{mover}} + d`}
              /></span
            >
            <NumberField
              id="desired-travel"
              value={config.desired_travel_mm}
              min={0.1}
              max={400}
              step={0.5}
              ariaLabel="Desired travel (center-to-center)"
              class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
              onCommit={(value) => (config.desired_travel_mm = value)}
            />
          </span>
        </label>

        <label class="min-w-0">
          <span class="flex items-center justify-between gap-2">
            <span class="min-w-0 truncate text-xs text-slate-300">Active area width (mm)</span>
            <NumberField
              id="active-area-width"
              value={config.active_area_width_mm}
              min={1}
              max={80}
              step={0.1}
              ariaLabel="Active area width (mm)"
              class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
              onCommit={(value) => (config.active_area_width_mm = value)}
            />
          </span>
        </label>

        <label class="min-w-0">
          <span class="flex items-center justify-between gap-2">
            <span class="min-w-0 truncate text-xs text-slate-300"
              >Electrical pitch <Formula tex="P_e" /> (mm)<HelpTag
                label="About electrical pitch"
                image={electricalPitchSvg}
                imageAlt="One electrical cycle spans a north and south pole."
                tip="One electrical cycle spans two alternating poles."
                equation={String.raw`\tau_p = \frac{P_e}{2}`}
              /></span
            >
            <NumberField
              id="electrical-pitch"
              value={config.electrical_pitch_mm}
              min={0.1}
              max={40}
              step={0.1}
              ariaLabel="Electrical pitch P_e (mm)"
              class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
              onCommit={(value) => {
                config.electrical_pitch_mm = value;
              }}
            />
          </span>
        </label>

      </div>
      <div class="mt-2">
        <div class="w-full">
          <TravelIsoView {config} {measuredTrace} stripStartMm={stripBounds.startMm} stripEndMm={stripBounds.endMm} />
        </div>
      </div>
      <ConstraintReadouts {config} measuredTraceLengthMm={measuredTrace?.traceLengthMm ?? null} {routingDimensions} />
    </section>
    <ValidationWarning {config} />
    {/snippet}
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
        <TopologySelector {config} cadGeometryActive={cadGeometry !== null} cadSourceFileName={cadGeometry?.source_file_name} {onImportCad} {onUseGenerated} />
        <RoutingOrientationPanel {config} geometry={cadGeometry} {onGeometryChange} />
        {@render constraints()}
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
