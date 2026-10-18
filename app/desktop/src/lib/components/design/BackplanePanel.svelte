<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import {
    BACKPLANE_MAX_THICKNESS_M,
    DEFAULT_HOUSING,
    HOUSING_MATERIAL_OPTIONS,
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
  } from "../../types/backplane";
  import NumberField from "../ui/NumberField.svelte";
  import HelpTag from "../ui/HelpTag.svelte";

  /**
   * Backplane and housing below the PCB (t707). Every edit replaces
   * `config.backplane` (and its layer array) instead of mutating it, so
   * dependents see one change per edit.
   */
  let {
    config,
    backplaneAnalysis = null,
  }: {
    config: ConfigStore;
    /** Output of the last simulation run. Null until a run has a backplane. */
    backplaneAnalysis?: BackplaneAnalysis | null;
  } = $props();

  const fieldClass = "w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200";
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
    Backplane &amp; housing<HelpTag
      label="About the backplane model"
      tip="Planar 1-D image model. Boundaries are treated as infinite planes, so edge effects and localized saturation are approximated. Eddy-current and core losses are not modelled."
    />
  </h2>

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
          <li class="flex items-center gap-1.5">
            <span class="w-4 shrink-0 text-right font-mono text-[10px] text-slate-500">{i + 1}</span>
            <select
              aria-label="Layer {i + 1} material"
              value={layer.material}
              onchange={(e) => patchLayer(i, { material: e.currentTarget.value as LayerMaterial })}
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
          </li>
        {/each}
      </ol>

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
          and are not modelled. Consider sintered MnZn or NiZn ferrite, or soft magnetic
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
        <dt class="text-slate-400">Inductance factor</dt>
        <dd class="font-mono text-slate-200">{backplaneAnalysis.inductance_factor.toFixed(2)}×</dd>
        <dt class="text-slate-400">Normal attraction</dt>
        <dd class="font-mono text-slate-200">{backplaneAnalysis.attraction_n.toPrecision(3)} N</dd>
        <dt class="text-slate-400">Image strength R</dt>
        <dd class="font-mono text-slate-200">{backplaneAnalysis.image_strength.toFixed(3)}</dd>
        {#if housing}
          <dt class="text-slate-400">Housing peak B</dt>
          <dd class="font-mono text-slate-200">{backplaneAnalysis.housing_peak_b_t.toPrecision(3)} T</dd>
        {/if}
      </dl>

      {#if backplaneAnalysis.layer_peak_b_t.length === backplane.layers.length}
        <ul class="mt-2 space-y-0.5 text-[11px] text-slate-300">
          {#each backplaneAnalysis.layer_peak_b_t as peak, i (i)}
            <li class="flex justify-between gap-2">
              <span>Layer {i + 1}, {layerMaterialLabel(backplane.layers[i].material)}</span>
              <span class="font-mono">{peak.toPrecision(3)} T peak</span>
            </li>
          {/each}
        </ul>
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
