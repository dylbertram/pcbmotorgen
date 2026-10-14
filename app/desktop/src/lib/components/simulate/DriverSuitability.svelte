<script lang="ts">
  import type { CheckStatus, DriveAnalysis, DriveCheck } from "../../types";
  import { formatSi } from "../../format";
  import VoltageEnvelopePlot from "./VoltageEnvelopePlot.svelte";

  let {
    analysis,
    error = null,
  }: { analysis: DriveAnalysis | null; error?: string | null } = $props();

  const STATUS: Record<CheckStatus, { glyph: string; tone: string; label: string }> = {
    pass: { glyph: "✓", tone: "text-emerald-300 border-emerald-500/50 bg-emerald-500/10", label: "Pass" },
    warn: { glyph: "!", tone: "text-amber-300 border-amber-500/50 bg-amber-500/10", label: "Marginal" },
    fail: { glyph: "✕", tone: "text-rose-300 border-rose-500/60 bg-rose-500/10", label: "Fail" },
    unknown: { glyph: "?", tone: "text-slate-400 border-slate-600 bg-slate-800", label: "Not evaluated" },
  };

  let verdict = $derived.by(() => {
    if (!analysis) return null;
    const statuses = analysis.checks.map((c) => c.status);
    const name = analysis.driver_name;
    if (statuses.includes("fail")) {
      const n = statuses.filter((s) => s === "fail").length;
      return { status: "fail" as const, text: `${name} can't drive these traces as configured: ${n} check${n === 1 ? "" : "s"} fail.` };
    }
    if (statuses.includes("warn")) return { status: "warn" as const, text: `${name} can drive these traces, with little margin.` };
    return { status: "pass" as const, text: `${name} can drive these traces.` };
  });

  // Line-to-line voltage split at the target speed (or standstill).
  let budget = $derived.by(() => {
    if (!analysis) return null;
    const a = analysis;
    const copper = Math.sqrt(3) * a.phase_current_a * a.phase_resistance_ohm;
    const fet = Math.max(0, a.holding_voltage_v - copper);
    const emf = a.back_emf_constant_v_s_per_m !== null ? Math.sqrt(3) * a.back_emf_constant_v_s_per_m * a.target_speed_m_s : 0;
    const total = a.speed_voltage_v ?? a.holding_voltage_v;
    const reactive = Math.max(0, total - copper - fet - emf);
    const scale = Math.max(a.bus_voltage_v, total);
    const pct = (v: number) => `${(Math.max(0, v) / scale) * 100}%`;
    return {
      total,
      segments: [
        { key: "copper", label: "Copper I·R", value: copper, color: "bg-amber-400", width: pct(copper) },
        { key: "fet", label: "Driver FETs", value: fet, color: "bg-slate-400", width: pct(fet) },
        { key: "emf", label: "Back-EMF", value: emf, color: "bg-sky-400", width: pct(emf) },
        { key: "reactive", label: "Inductive ωL·I", value: reactive, color: "bg-violet-400", width: pct(reactive) },
      ],
      usable: pct(a.available_voltage_v),
      bus: pct(a.bus_voltage_v),
      over: total > a.available_voltage_v,
    };
  });

  function formatCheck(c: DriveCheck, v: number): string {
    return c.unit === "Hz" ? formatSi(v, "Hz") : `${v.toFixed(v >= 100 ? 0 : 2)} ${c.unit}`;
  }

  /** Bar fill of value against limit, capped so overruns stay visible. */
  function fill(c: DriveCheck): number {
    if (!(c.limit > 0) || c.status === "unknown") return 0;
    return Math.min(1.25, c.value / c.limit) / 1.25;
  }

  // For "value must exceed limit" checks (thrust) the bar reads the other way.
  const AT_LEAST = new Set(["thrust"]);
</script>

<section aria-labelledby="driver-suitability-heading" class="rounded-lg border border-slate-700 bg-slate-800/40 p-4">
  <div class="flex flex-wrap items-baseline justify-between gap-2">
    <h3 id="driver-suitability-heading" class="text-sm font-semibold text-slate-200">Driver suitability</h3>
    {#if analysis}
      <span class="text-xs text-slate-400">
        {analysis.phase_current_a.toFixed(2)} A per phase at {analysis.bus_voltage_v.toFixed(1)} V, {formatSi(analysis.pwm_hz, "Hz")} PWM
      </span>
    {/if}
  </div>

  {#if error}
    <p class="mt-3 rounded-md border border-rose-500/60 bg-rose-500/10 px-3 py-2 text-xs text-rose-200" role="alert">
      Driver analysis failed: {error}
    </p>
  {/if}

  {#if !analysis}
    <p class="mt-3 text-xs text-slate-500">Measuring the routed copper…</p>
  {:else if verdict && budget}
    <p class="mt-3 flex items-start gap-2 text-sm text-slate-100" role="status">
      <span class="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs font-bold {STATUS[verdict.status].tone}" aria-hidden="true">{STATUS[verdict.status].glyph}</span>
      {verdict.text}
    </p>

    <!-- Voltage budget: where the bus voltage goes at the target speed. -->
    <div class="mt-4">
      <div class="flex items-baseline justify-between text-xs">
        <span class="text-slate-300">
          Voltage budget at {analysis.speed_voltage_v !== null ? `${analysis.target_speed_m_s.toFixed(2)} m/s` : "standstill"}
        </span>
        <span class="font-mono {budget.over ? 'text-rose-300' : 'text-slate-200'}">
          {budget.total.toFixed(2)} V of {analysis.available_voltage_v.toFixed(2)} V usable
        </span>
      </div>
      <div class="relative mt-1.5 h-6">
        <div class="flex h-full w-full overflow-hidden rounded-sm bg-slate-900 ring-1 ring-slate-700">
          {#each budget.segments as seg (seg.key)}
            <div class="{seg.color} h-full" style:width={seg.width} title="{seg.label}: {seg.value.toFixed(2)} V"></div>
          {/each}
        </div>
        <div class="pointer-events-none absolute inset-y-[-3px] w-0 border-l-2 border-dashed border-emerald-300" style:left={budget.usable} aria-hidden="true"></div>
        <div class="pointer-events-none absolute inset-y-[-3px] w-0 border-l-2 border-slate-300" style:left={budget.bus} aria-hidden="true"></div>
      </div>
      <ul class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
        {#each budget.segments as seg (seg.key)}
          <li class="flex items-center gap-1.5">
            <span class="h-2.5 w-2.5 rounded-sm {seg.color}" aria-hidden="true"></span>
            {seg.label} <span class="font-mono text-slate-200">{seg.value.toFixed(2)} V</span>
          </li>
        {/each}
        <li class="flex items-center gap-1.5"><span class="h-3 border-l-2 border-dashed border-emerald-300" aria-hidden="true"></span>usable</li>
        <li class="flex items-center gap-1.5"><span class="h-3 border-l-2 border-slate-300" aria-hidden="true"></span>bus</li>
      </ul>
    </div>

    <div class="mt-5 space-y-5">
      <!-- Checks -->
      <ul class="min-w-0 divide-y divide-slate-700/70 border-y border-slate-700/70" aria-label="Driver checks">
        {#each analysis.checks as c (c.id)}
          <li class="py-2.5">
            <div class="flex items-start gap-2.5">
              <span class="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border text-[10px] font-bold {STATUS[c.status].tone}" title={STATUS[c.status].label}>
                <span aria-hidden="true">{STATUS[c.status].glyph}</span>
                <span class="sr-only">{STATUS[c.status].label}</span>
              </span>
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-baseline justify-between gap-x-3">
                  <span class="text-xs text-slate-200">{c.label}</span>
                  {#if c.status !== "unknown"}
                    <span class="font-mono text-xs text-slate-300">
                      {formatCheck(c, c.value)}
                      <span class="text-slate-500">{AT_LEAST.has(c.id) ? "≥" : "≤"} {formatCheck(c, c.limit)}</span>
                    </span>
                  {/if}
                </div>
                {#if c.status !== "unknown"}
                  <div class="relative mt-1 h-1 rounded-full bg-slate-700/70" aria-hidden="true">
                    <div
                      class="h-1 rounded-full {c.status === 'pass' ? 'bg-emerald-400' : c.status === 'warn' ? 'bg-amber-400' : 'bg-rose-400'}"
                      style:width="{fill(c) * 100}%"
                    ></div>
                    <div class="absolute top-[-2px] h-2 w-px bg-slate-300" style:left="80%"></div>
                  </div>
                {/if}
                <p class="mt-1 text-[11px] leading-snug text-slate-400">{c.detail}</p>
              </div>
            </div>
          </li>
        {/each}
      </ul>

      <div class="min-w-0 space-y-5">
        <VoltageEnvelopePlot {analysis} />

        <dl class="grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
          <div>
            <dt class="text-slate-400">Highest continuous current</dt>
            <dd class="font-mono text-slate-100">{analysis.max_continuous_current_a.toFixed(2)} A</dd>
            <dd class="text-[11px] text-slate-500">limited by {analysis.limiting_factor}</dd>
          </div>
          <div>
            <dt class="text-slate-400">Thrust at that current</dt>
            <dd class="font-mono text-slate-100">{analysis.max_continuous_thrust_n !== null ? `${analysis.max_continuous_thrust_n.toFixed(3)} N` : "—"}</dd>
            <dd class="text-[11px] text-slate-500">K_f {analysis.thrust_constant_n_per_a !== null ? `${analysis.thrust_constant_n_per_a.toFixed(3)} N/A` : "pending"}</dd>
          </div>
          <div>
            <dt class="text-slate-400">PWM for the ripple limit</dt>
            <dd class="font-mono text-slate-100">≥ {formatSi(analysis.min_pwm_hz, "Hz")}</dd>
            {#if analysis.added_inductance_h > 0}
              <dd class="text-[11px] text-slate-500">or add {formatSi(analysis.added_inductance_h, "H")} per phase</dd>
            {/if}
          </div>
          <div>
            <dt class="text-slate-400">Copper loss</dt>
            <dd class="font-mono text-slate-100">{formatSi(analysis.copper_loss_w, "W")}</dd>
            <dd class="text-[11px] text-slate-500">τ = L/R {formatSi(analysis.time_constant_s, "s")}</dd>
          </div>
        </dl>
      </div>
    </div>

    <!-- Measured copper -->
    <div class="mt-5">
      <h4 class="text-xs font-semibold text-slate-300">Measured from the routed traces</h4>
      <div class="mt-2 overflow-x-auto">
        <table class="w-full whitespace-nowrap text-left text-xs">
          <thead class="text-slate-400">
            <tr class="border-b border-slate-700">
              <th scope="col" class="py-1.5 pr-3 font-normal">Phase</th>
              <th scope="col" class="py-1.5 pr-3 text-right font-normal">Strands</th>
              <th scope="col" class="py-1.5 pr-3 text-right font-normal">Length each</th>
              <th scope="col" class="py-1.5 pr-3 text-right font-normal">Vias each</th>
              <th scope="col" class="py-1.5 pr-3 text-right font-normal">R 20 °C</th>
              <th scope="col" class="py-1.5 pr-3 text-right font-normal">R hot</th>
              <th scope="col" class="py-1.5 text-right font-normal">L self</th>
            </tr>
          </thead>
          <tbody class="font-mono text-slate-200">
            {#each analysis.phases as p (p.net)}
              <tr class="border-b border-slate-800">
                <th scope="row" class="py-1.5 pr-3 font-sans font-medium text-slate-300">
                  {p.net}
                  {#if !p.connected}<span class="ml-1 font-sans text-rose-300">open</span>{/if}
                </th>
                <td class="py-1.5 pr-3 text-right">{p.strands}</td>
                <td class="py-1.5 pr-3 text-right">{(p.strand_length_m * 1e3).toFixed(0)} mm</td>
                <td class="py-1.5 pr-3 text-right">{p.vias_per_strand.toFixed(0)}</td>
                <td class="py-1.5 pr-3 text-right">{formatSi(p.resistance_20c_ohm, "Ω")}</td>
                <td class="py-1.5 pr-3 text-right" title="Vias contribute {formatSi(p.via_resistance_ohm, 'Ω')}">{formatSi(p.resistance_hot_ohm, "Ω")}</td>
                <td class="py-1.5 text-right">{formatSi(p.self_inductance_h, "H")}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="mt-2 text-xs text-slate-400">
        Trace {(analysis.trace_width_m * 1e3).toFixed(3)} mm wide,
        {(analysis.outer_copper_m * 1e6).toFixed(0)} µm outer and {(analysis.inner_copper_m * 1e6).toFixed(0)} µm inner copper,
        {formatSi(analysis.via_resistance_each_ohm, "Ω")} per via
        ({formatSi(analysis.phases[0]?.via_resistance_ohm ?? 0, "Ω")} of phase {analysis.phases[0]?.net ?? "A"}'s hot resistance).
        R hot is at the winding temperature.
      </p>
    </div>

    <!-- Bench targets -->
    <div class="mt-4 rounded-md border border-slate-700 bg-slate-900/50 px-3 py-2.5">
      <h4 class="text-xs font-semibold text-slate-300">Check on the prototype</h4>
      <p class="mt-1 text-xs text-slate-400">
        Measure between two phase terminals on the unpowered board. Star wiring puts two phases in series.
      </p>
      <dl class="mt-2 grid gap-y-1 text-xs">
        <div class="flex justify-between gap-3">
          <dt class="text-slate-400">4-wire resistance, A–B at 20 °C</dt>
          <dd class="whitespace-nowrap font-mono text-slate-100">{formatSi(2 * (analysis.phases[0]?.resistance_20c_ohm ?? 0), "Ω")}</dd>
        </div>
        <div class="flex justify-between gap-3">
          <dt class="text-slate-400">LCR at 100 kHz, A–B</dt>
          <dd class="whitespace-nowrap font-mono text-slate-100">{formatSi(analysis.line_inductance_h, "H")}</dd>
        </div>
      </dl>
    </div>

    {#if analysis.notes.length}
      <ul class="mt-3 list-disc space-y-0.5 pl-4 text-[11px] text-slate-500">
        {#each analysis.notes as note (note)}<li>{note}</li>{/each}
      </ul>
    {/if}
  {/if}
</section>
