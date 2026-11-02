<script lang="ts">
  import type { ConfigStore } from "../../../stores/config.svelte";
  import type { MotionStore } from "../../../stores/motion.svelte";
  import type { RoutingDimensionsDto } from "../../../types";
  import { stripBoundsDomainMm } from "../../../geometry/moverBounds";
  import type { TraceMeasure } from "../../../preview/previewGeometry";
  import NumberField from "../../ui/NumberField.svelte";
  import HelpTag from "../../ui/HelpTag.svelte";
  import Formula from "../../ui/Formula.svelte";
  import electricalPitchSvg from "../../../assets/electrical-pitch.svg";
  import TravelIsoView from "./TravelIsoView.svelte";
  import ConstraintReadouts from "./ConstraintReadouts.svelte";
  import ValidationWarning from "./ValidationWarning.svelte";

  let { config, motion, measuredTrace, routingDimensions }: {
    config: ConfigStore;
    motion: MotionStore;
    measuredTrace: TraceMeasure | null;
    routingDimensions: RoutingDimensionsDto | null;
  } = $props();
  const stripBounds = $derived(stripBoundsDomainMm(config, motion));
</script>

<section id="design-constraints-heading" aria-label="Design constraints">
  <div class="grid gap-x-3 gap-y-2.5">
    <label class="min-w-0">
      <span class="flex items-center justify-between gap-2">
        <span class="min-w-0 truncate text-xs text-slate-300">Travel (mm)<HelpTag
          label="About desired travel"
          tip="Center-to-center travel. The copper must cover the mover span plus this distance."
          equation={String.raw`L_{\mathrm{active}} = L_{\mathrm{mover}} + d`}
        /></span>
        <NumberField id="desired-travel" value={config.desired_travel_mm} min={0.1} max={400} step={0.5}
          ariaLabel="Desired travel (center-to-center)" class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
          onCommit={(value) => (config.desired_travel_mm = value)} />
      </span>
    </label>

    <label class="min-w-0">
      <span class="flex items-center justify-between gap-2">
        <span class="min-w-0 truncate text-xs text-slate-300">Active area width (mm)</span>
        <NumberField id="active-area-width" value={config.active_area_width_mm} min={1} max={80} step={0.1}
          ariaLabel="Active area width (mm)" class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
          onCommit={(value) => (config.active_area_width_mm = value)} />
      </span>
    </label>

    <label class="min-w-0">
      <span class="flex items-center justify-between gap-2">
        <span class="min-w-0 truncate text-xs text-slate-300">Electrical pitch <Formula tex="P_e" /> (mm)<HelpTag
          label="About electrical pitch" image={electricalPitchSvg} imageAlt="One electrical cycle spans a north and south pole."
          tip="A cycle spans two poles. Oversized magnets cause a design error. Generated copper follows pitch; imported copper does not."
          equation={String.raw`\tau_p = \frac{P_e}{2}`}
        /></span>
        <NumberField id="electrical-pitch" value={config.electrical_pitch_mm} min={0.1} max={40} step={0.1}
          ariaLabel="Electrical pitch P_e (mm)" class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
          onCommit={(value) => { config.electrical_pitch_mm = value; }} />
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
