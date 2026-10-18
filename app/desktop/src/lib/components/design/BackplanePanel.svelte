<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import {
    BACKPLANE_MAX_BSAT_T,
    BACKPLANE_MAX_MU_R,
    BACKPLANE_MAX_THICKNESS_M,
    DEFAULT_HOUSING,
    HOUSING_MATERIAL_OPTIONS,
    LAYER_DEFAULT_BSAT_T,
    LAYER_DEFAULT_MU_R,
    LAYER_MATERIAL_OPTIONS,
    SILICON_STEEL_PWM_LIMIT_HZ,
    layerMaterialLabel,
    newLayer,
    type BackplaneAnalysis,
    type BackplaneLayer,
    type BackplaneStack,
    type HousingMaterial,
    type HousingSpec,
    type LayerMaterial,
    type MagneticState,
  } from "../../types/backplane";
  import type { DriveBackplane } from "../../types/drive";
  import NumberField from "../ui/NumberField.svelte";
  import HelpTag from "../ui/HelpTag.svelte";
  import TravelStackupView from "./TravelStackupView.svelte";

  /**
   * Backplane and housing below the PCB (t707). Every edit replaces
   * `config.backplane` (and its layer array) instead of mutating it, so
   * dependents see one change per edit.
   */
  let {
    config,
    backplaneAnalysis = null,
    driveBackplane = null,
  }: {
    config: ConfigStore;
    /** Output of the last simulation run. Null until a run has a backplane. */
    backplaneAnalysis?: BackplaneAnalysis | null;
    /** Eddy-current results of the last driver analysis, if any. */
    driveBackplane?: DriveBackplane | null;
  } = $props();

  const fieldClass = "w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200";
  const overrideClass = "w-16 shrink-0 px-1.5 py-0.5 text-[11px] font-mono text-emerald-200";
  const selectClass =
    "w-40 shrink-0 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400";
  const layerSelectClass =
    "min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-xs text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400";
  const buttonClass =
    "shrink-0 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-40";

  // The store holds metres and the fields show millimetres. Rounding trims
  // float noise (0.35e-3 * 1e3 is not exactly 0.35).
  const toMm = (m: number) => Number((m * 1e3).toPrecision(12));
  const toM = (mm: number) => mm / 1e3;

  let backplane = $derived(config.backplane);
  let housing = $derived(backplane?.housing ?? null);
  let hasFlexSheet = $derived(
    backplane?.layers.some((layer) => layer.material === "flex_ferrite") ?? false,
  );

  /** One line on how a layer carries the magnet flux. */
  function stateSummary(state: MagneticState): string {
    if (state.bsat_t === null || state.mu_initial <= 1) return "linear";
    if (state.flux_overload > 1) {
      return `saturated, ${state.flux_overload.toFixed(1)}× flux, μr ${state.mu_initial.toFixed(0)}→${state.mu_effective.toFixed(1)}`;
    }
    return `${state.peak_b_t.toPrecision(3)} T peak, Bsat ${state.bsat_t.toFixed(2)} T`;
  }

  const isMagnetic = (material: LayerMaterial) => LAYER_DEFAULT_BSAT_T[material] !== null;

  // Silicon steel loses efficiency at high switching frequency. This checks
  // the PWM frequency from DriveSettings. Keep SILICON_STEEL_PWM_LIMIT_HZ in
  // sync with the Rust source (crates/pcbmotorgen-simulation/src/backplane/mod.rs).
  let siliconSteelAtHighPwm = $derived(
    (backplane?.layers.some((layer) => layer.material === "silicon_steel") ?? false) &&
      config.drive.pwm_hz > SILICON_STEEL_PWM_LIMIT_HZ,
  );

  function setBackplane(next: BackplaneStack | null) {
    config.backplane = next;
  }

  function setLayers(layers: BackplaneLayer[]) {
    const current = config.backplane;
    if (!current) return;
    config.backplane = { ...current, layers };
  }

  function patchLayer(index: number, patch: Partial<BackplaneLayer>) {
    const layers = config.backplane?.layers;
    if (!layers) return;
    setLayers(layers.map((layer, i) => (i === index ? { ...layer, ...patch } : layer)));
  }

  function moveLayer(index: number, delta: -1 | 1) {
    const layers = config.backplane?.layers;
    const target = index + delta;
    if (!layers || target < 0 || target >= layers.length) return;
    const next = [...layers];
    [next[index], next[target]] = [next[target], next[index]];
    setLayers(next);
  }

  function removeLayer(index: number) {
    const layers = config.backplane?.layers;
    // A backplane keeps at least one layer. Use "Remove backplane" to clear it.
    if (!layers || layers.length <= 1) return;
    setLayers(layers.filter((_, i) => i !== index));
  }

  function addLayer() {
    setLayers([...(config.backplane?.layers ?? []), newLayer("mn_zn_ferrite")]);
  }

  function addBackplane() {
    setBackplane({ layers: [newLayer("mn_zn_ferrite")], housing: null });
  }

  function setHousingEnabled(enabled: boolean) {
    const current = config.backplane;
    if (!current) return;
    config.backplane = { ...current, housing: enabled ? { ...DEFAULT_HOUSING } : null };
  }

  function patchHousing(patch: Partial<HousingSpec>) {
    const current = config.backplane;
    if (!current?.housing) return;
    config.backplane = { ...current, housing: { ...current.housing, ...patch } };
  }
</script>

<section
  class="rounded-md border border-slate-700 bg-slate-800/40 px-3 py-2.5"
  aria-labelledby="backplane-heading"
>
  <h2
    id="backplane-heading"
    class="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-200"
  >
    Stackup<HelpTag
      label="About the backplane model"
      tip="Planar layered model of the magnet fundamental. Saturation uses one effective permeability per layer; eddy currents use the layers' conductivity at the PWM frequency and at the mover speed. Boundaries are infinite planes, so edges are ignored. Core and hysteresis losses are not modelled."
    />
  </h2>

  <div class="mb-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px] items-start">
    <div class="space-y-2.5">
      <label class="flex items-center justify-between gap-2 text-xs text-slate-300">
        <span>Air gap (mm)</span>
        <NumberField id="air-gap" value={config.air_gap_mm} min={0} step={0.05} ariaLabel="Air gap (mm)" class={fieldClass} onCommit={(value) => (config.air_gap_mm = value)} />
      </label>
      <label class="flex items-center justify-between gap-2 text-xs text-slate-300">
        <span>PCB thickness (mm)</span>
        <NumberField id="pcb-thickness" value={config.pcb_thickness_mm} min={0.1} step={0.1} ariaLabel="PCB thickness (mm)" class={fieldClass} onCommit={(value) => (config.pcb_thickness_mm = value)} />
      </label>
    </div>
    <TravelStackupView {config} />
  </div>

  {#if !backplane}
    <p class="mb-2 text-[11px] leading-relaxed text-slate-400">
      No backplane is set, so the field model is unchanged.
    </p>
    <button type="button" class={buttonClass} onclick={addBackplane}>Add backplane</button>
  {:else}
    <div class="space-y-2">
      <p class="text-[11px] leading-relaxed text-slate-400">
        Layer 1 touches the PCB. Order runs from the PCB downward.
      </p>

      <ol class="space-y-1.5" aria-label="Backplane layers, from the PCB downward">
        {#each backplane.layers as layer, i (i)}
          <li class="space-y-1">
            <div class="flex items-center gap-1.5">
              <span class="w-4 shrink-0 text-right font-mono text-[10px] text-slate-500">{i + 1}</span>
              <select
                aria-label="Layer {i + 1} material"
                value={layer.material}
                onchange={(e) =>
                  patchLayer(i, { material: e.currentTarget.value as LayerMaterial, mu_r: null, bsat_t: null })}
                class={layerSelectClass}
              >
                {#each LAYER_MATERIAL_OPTIONS as option (option.value)}
                  <option value={option.value}>{option.label}</option>
                {/each}
              </select>
              <NumberField
                value={toMm(layer.thickness_m)}
                min={0.01}
                max={BACKPLANE_MAX_THICKNESS_M * 1e3}
                step={0.05}
                ariaLabel="Layer {i + 1} thickness (mm)"
                class={fieldClass}
                onCommit={(mm) => patchLayer(i, { thickness_m: toM(mm) })}
              />
              <button
                type="button"
                class={buttonClass}
                aria-label="Move layer {i + 1} up"
                disabled={i === 0}
                onclick={() => moveLayer(i, -1)}
              >↑</button>
              <button
                type="button"
                class={buttonClass}
                aria-label="Move layer {i + 1} down"
                disabled={i === backplane.layers.length - 1}
                onclick={() => moveLayer(i, 1)}
              >↓</button>
              <button
                type="button"
                class={buttonClass}
                aria-label="Remove layer {i + 1}"
                disabled={backplane.layers.length <= 1}
                onclick={() => removeLayer(i)}
              >Remove</button>
            </div>
            {#if isMagnetic(layer.material)}
              <div class="flex items-center gap-1.5 pl-[22px] text-[11px] text-slate-400">
                <span class="shrink-0">μr</span>
                <NumberField
                  value={layer.mu_r ?? LAYER_DEFAULT_MU_R[layer.material]}
                  min={1}
                  max={BACKPLANE_MAX_MU_R}
                  step={10}
                  ariaLabel="Layer {i + 1} relative permeability"
                  class={overrideClass}
                  onCommit={(mu) => patchLayer(i, { mu_r: mu })}
                />
                <span class="shrink-0">Bsat (T)</span>
                <NumberField
                  value={layer.bsat_t ?? LAYER_DEFAULT_BSAT_T[layer.material] ?? 0}
                  min={0.01}
                  max={BACKPLANE_MAX_BSAT_T}
                  step={0.01}
                  ariaLabel="Layer {i + 1} saturation flux density (T)"
                  class={overrideClass}
                  onCommit={(bsat) => patchLayer(i, { bsat_t: bsat })}
                />
                {#if layer.mu_r != null || layer.bsat_t != null}
                  <button
                    type="button"
                    class={buttonClass}
                    aria-label="Use typical values for layer {i + 1}"
                    onclick={() => patchLayer(i, { mu_r: null, bsat_t: null })}
                  >Typical</button>
                {:else}
                  <span class="text-slate-500">typical</span>
                {/if}
              </div>
            {/if}
          </li>
        {/each}
      </ol>
      {#if hasFlexSheet}
        <p class="text-[11px] leading-relaxed text-slate-400">
          Enter the ferrite thickness of a sheet only. Datasheet totals include adhesive and
          cover film. Put datasheet μr and Bsat in the fields above.
        </p>
      {/if}

      <button type="button" class={buttonClass} onclick={addLayer}>Add layer</button>
    </div>

    <div class="mt-3 space-y-2.5 border-t border-slate-700/70 pt-2.5">
      <label class="flex items-center gap-2 text-xs text-slate-300">
        <input
          type="checkbox"
          checked={housing !== null}
          onchange={(e) => setHousingEnabled(e.currentTarget.checked)}
        />
        Housing below the backplane
      </label>

      {#if housing}
        <label class="min-w-0">
          <span class="flex items-center justify-between gap-2">
            <span class="min-w-0 truncate text-xs text-slate-300">Housing material</span>
            <select
              aria-label="Housing material"
              value={housing.material}
              onchange={(e) => patchHousing({ material: e.currentTarget.value as HousingMaterial })}
              class={selectClass}
            >
              {#each HOUSING_MATERIAL_OPTIONS as option (option.value)}
                <option value={option.value}>{option.label}</option>
              {/each}
            </select>
          </span>
        </label>

        <label class="min-w-0">
          <span class="flex items-center justify-between gap-2">
            <span class="min-w-0 truncate text-xs text-slate-300">Housing wall (mm)</span>
            <NumberField
              value={toMm(housing.thickness_m)}
              min={0.1}
              max={BACKPLANE_MAX_THICKNESS_M * 1e3}
              step={0.1}
              ariaLabel="Housing wall thickness (mm)"
              class={fieldClass}
              onCommit={(mm) => patchHousing({ thickness_m: toM(mm) })}
            />
          </span>
        </label>

        <label class="min-w-0">
          <span class="flex items-center justify-between gap-2">
            <span class="min-w-0 truncate text-xs text-slate-300">Gap to backplane (mm)</span>
            <NumberField
              value={toMm(housing.gap_m)}
              min={0}
              max={BACKPLANE_MAX_THICKNESS_M * 1e3}
              step={0.1}
              ariaLabel="Housing gap to backplane (mm)"
              class={fieldClass}
              onCommit={(mm) => patchHousing({ gap_m: toM(mm) })}
            />
          </span>
        </label>
      {/if}

      {#if siliconSteelAtHighPwm}
        <p
          role="status"
          class="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 text-[11px] leading-relaxed text-amber-200"
        >
          Silicon steel is selected with PWM at {(config.drive.pwm_hz / 1e3).toFixed(1)} kHz,
          above {SILICON_STEEL_PWM_LIMIT_HZ / 1e3} kHz. Eddy and core losses rise steeply here
          are only partly modelled. Consider sintered MnZn or NiZn ferrite, or soft magnetic
          composite (SMC).
        </p>
      {/if}

      <button type="button" class={buttonClass} onclick={() => setBackplane(null)}>
        Remove backplane
      </button>
    </div>
  {/if}

  {#if backplane && backplaneAnalysis}
    <div class="mt-3 border-t border-slate-700/70 pt-2.5">
      <p class="mb-1.5 text-[10px] uppercase tracking-wider text-slate-500">
        From the last simulation run; may lag recent edits
      </p>
      <dl class="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <dt class="text-slate-400">Image strength R</dt>
        <dd class="font-mono text-slate-200">
          {backplaneAnalysis.image_strength.toFixed(3)}
          {#if backplaneAnalysis.linear_image_strength !== backplaneAnalysis.image_strength}
            <span class="text-slate-500">(unsaturated {backplaneAnalysis.linear_image_strength.toFixed(3)})</span>
          {/if}
        </dd>
        <dt class="text-slate-400">Inductance factor</dt>
        <dd class="font-mono text-slate-200">{backplaneAnalysis.inductance_factor.toFixed(2)}×</dd>
        <dt class="text-slate-400">Normal attraction</dt>
        <dd class="font-mono text-slate-200">{backplaneAnalysis.attraction_n.toPrecision(3)} N</dd>
        {#if housing && backplaneAnalysis.housing_state && backplaneAnalysis.housing_state.mu_initial > 1}
          <dt class="text-slate-400">Housing</dt>
          <dd class="font-mono text-slate-200">{stateSummary(backplaneAnalysis.housing_state)}</dd>
        {/if}
      </dl>

      {#if backplaneAnalysis.layer_states.length === backplane.layers.length}
        <ul class="mt-2 space-y-0.5 text-[11px] text-slate-300">
          {#each backplaneAnalysis.layer_states as state, i (i)}
            <li class="flex justify-between gap-2">
              <span>Layer {i + 1}, {layerMaterialLabel(backplane.layers[i].material)}</span>
              <span class="font-mono" class:text-amber-200={state.flux_overload > 1}>{stateSummary(state)}</span>
            </li>
          {/each}
        </ul>
      {/if}

      {#if driveBackplane}
        <p class="mt-2.5 mb-1 text-[10px] uppercase tracking-wider text-slate-500">
          Eddy currents, from the last driver analysis
        </p>
        <dl class="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
          <dt class="text-slate-400">L at {(config.drive.pwm_hz / 1e3).toFixed(0)} kHz PWM</dt>
          <dd class="font-mono text-slate-200">
            {(driveBackplane.pwm_inductance_h * 1e6).toFixed(2)} µH ({driveBackplane.pwm_inductance_factor.toFixed(2)}×)
          </dd>
          <dt class="text-slate-400">Added R at PWM</dt>
          <dd class="font-mono text-slate-200">{(driveBackplane.pwm_resistance_ohm * 1e3).toPrecision(3)} mΩ</dd>
          <dt class="text-slate-400">Eddy loss from ripple</dt>
          <dd class="font-mono text-slate-200">{driveBackplane.ripple_eddy_loss_w.toPrecision(3)} W</dd>
          <dt class="text-slate-400">Drag at {config.drive.target_speed_m_s} m/s</dt>
          <dd class="font-mono text-slate-200">
            {driveBackplane.drag_n.toPrecision(3)} N ({driveBackplane.drag_power_w.toPrecision(3)} W)
          </dd>
          {#if driveBackplane.net_thrust_n != null}
            <dt class="text-slate-400">Thrust minus drag</dt>
            <dd class="font-mono" class:text-amber-200={driveBackplane.net_thrust_n < 0} class:text-slate-200={driveBackplane.net_thrust_n >= 0}>
              {driveBackplane.net_thrust_n.toPrecision(3)} N
            </dd>
          {/if}
          {#if driveBackplane.drag_limited_speed_m_s != null}
            <dt class="text-slate-400">Drag equals thrust at</dt>
            <dd class="font-mono text-amber-200">{driveBackplane.drag_limited_speed_m_s.toPrecision(3)} m/s</dd>
          {/if}
        </dl>
      {/if}

      {#if backplaneAnalysis.warnings.length}
        <ul class="mt-2 list-disc space-y-0.5 pl-4 text-[11px] text-amber-200">
          {#each backplaneAnalysis.warnings as warning, i (i)}
            <li>{warning}</li>
          {/each}
        </ul>
      {/if}
    </div>
  {:else if backplane}
    <p class="mt-3 border-t border-slate-700/70 pt-2.5 text-[11px] text-slate-500">
      Backplane results appear after the next simulation run.
    </p>
  {/if}
</section>
