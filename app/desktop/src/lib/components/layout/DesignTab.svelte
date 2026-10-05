<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { CadGeometry } from "../../types";
  import TopologySelector from "../design/TopologySelector.svelte";
  import TracesBoardPanel from "../design/parameters/TracesBoardPanel.svelte";
  import MagnetsPanel from "../design/parameters/MagnetsPanel.svelte";
  import ValidationWarning from "../design/ValidationWarning.svelte";
  import NumberField from "../ui/NumberField.svelte";
  import HelpTag from "../ui/HelpTag.svelte";
  import ScrollArea from "../ui/ScrollArea.svelte";
  import electricalPitchSvg from "../../assets/electrical-pitch.svg";

  let {
    config,
    cadGeometry = null,
  }: {
    config: ConfigStore;
    cadGeometry?: CadGeometry | null;
  } = $props();
</script>

<ScrollArea
  id="design-settings-scroll"
  class="h-full lg:pr-1"
  aria-label="Design settings"
>
  <div class="space-y-3">
    <!-- General geometry + clearance. No driver toggle: every field here is
         a normal user input. Derived values (travel, pole pitch, mover span,
         rest offset, preview metrics) stay read-only in the reflection. -->
    <section
      class="rounded-md border border-slate-700 bg-slate-800/40 px-3 py-2.5"
      aria-labelledby="design-constraints-heading"
    >
      <h2
        id="design-constraints-heading"
        class="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-200"
      >
        Design constraints
      </h2>
      <div class="grid gap-x-3 gap-y-2.5 sm:grid-cols-2">
        <label
          class="min-w-0"
        >
          <span class="flex items-center justify-between gap-2">
            <span class="min-w-0 truncate text-xs text-slate-300"
              >Desired travel (center-to-center)<HelpTag
                tip="Center-to-center travel you want; active-area length follows (mover span + travel)."
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
            <span class="min-w-0 truncate text-xs text-slate-300">PCB thickness (mm)</span>
            <NumberField
              id="pcb-thickness"
              value={config.pcb_thickness_mm}
              min={0.1}
              step={0.1}
              ariaLabel="PCB thickness (mm)"
              class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
              onCommit={(value) => (config.pcb_thickness_mm = value)}
            />
          </span>
        </label>

        <label class="min-w-0">
          <span class="flex items-center justify-between gap-2">
            <span class="min-w-0 truncate text-xs text-slate-300"
              >Electrical pitch <span class="italic">P<sub>e</sub></span> (mm)<HelpTag
                label="About electrical pitch"
                image={electricalPitchSvg}
                imageAlt="Diagram: one electrical cycle spans two alternating poles N and S; the pole pitch is half of it."
              >
                Length of one full electrical cycle: two alternating poles. Pole
                pitch <span class="italic">τ<sub>p</sub></span> =
                <span class="italic">P<sub>e</sub></span> ÷ 2.
              </HelpTag></span
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

        <label class="min-w-0">
          <span class="flex items-center justify-between gap-2">
            <span class="min-w-0 truncate text-xs text-slate-300">Air gap (mm)</span>
            <NumberField
              id="air-gap"
              value={config.air_gap_mm}
              min={0}
              step={0.05}
              ariaLabel="Air gap (mm)"
              class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
              onCommit={(value) => (config.air_gap_mm = value)}
            />
          </span>
        </label>
      </div>
    </section>

    <!-- Topology (routing pattern + parameters + generator load) and the
         board/winding fields share one panel so winding geometry can be
         reviewed and edited side by side. -->
    <section
      class="rounded-md border border-slate-700 bg-slate-800/40 px-3 py-2.5"
      aria-labelledby="topology-board-heading"
    >
      <h2
        id="topology-board-heading"
        class="mb-2.5 text-xs font-semibold uppercase tracking-wider text-slate-200"
      >
        Topology &amp; Board
      </h2>
      <div class="space-y-3">
        {#if cadGeometry}
          <div
            class="rounded-md border border-sky-500/30 bg-sky-500/5 px-3 py-3"
            role="group"
            aria-label="Imported CAD pattern"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p class="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  Routing pattern
                </p>
                <p class="mt-0.5 text-sm font-medium text-sky-200">Imported CAD pattern</p>
              </div>
              <span class="rounded-full border border-sky-400/30 bg-sky-400/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-sky-200">
                Imported
              </span>
            </div>
            <p class="mt-2 text-[11px] leading-relaxed text-slate-400">
              The DXF geometry is active. Generator topology and winding settings are hidden because they do not describe the imported traces. To return to a generated pattern, choose File → Import CAD → Use generated geometry.
            </p>
            <dl class="mt-3 grid grid-cols-3 gap-2 border-t border-slate-700/70 pt-2">
              <div>
                <dt class="text-[10px] text-slate-500">Copper layers</dt>
                <dd class="font-mono text-xs text-slate-200">{cadGeometry.layer_z_mm.length}</dd>
              </div>
              <div>
                <dt class="text-[10px] text-slate-500">Trace elements</dt>
                <dd class="font-mono text-xs text-slate-200">
                  {cadGeometry.routing.segments.length + cadGeometry.routing.curves.length}
                </dd>
              </div>
              <div>
                <dt class="text-[10px] text-slate-500">Vias</dt>
                <dd class="font-mono text-xs text-slate-200">{cadGeometry.routing.vias.length}</dd>
              </div>
            </dl>
          </div>
        {:else}
          <TopologySelector {config} />
          <TracesBoardPanel {config} />
        {/if}
      </div>
    </section>

    <MagnetsPanel {config} />
    <ValidationWarning {config} />
  </div>
</ScrollArea>
