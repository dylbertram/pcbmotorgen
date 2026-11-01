import type { RoutedMoveRequest } from "./types/movePower";
import type { MoveSummary } from "./moveSummary";

export interface MoveReportMeta {
  designName: string;
  geometrySource: string;
  appVersion: string;
  inputSha256: string;
  driverName: string;
  supplyVoltageV: number;
  pwmHz: number;
  windingTempC: number;
  modelVersion: string;
  generatedAt: string;
  request: RoutedMoveRequest;
}

const escape = (text: string): string => text
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;").replaceAll("'", "&#39;");

function signed(value: number, unit: string): string {
  return `${value.toFixed(4).replace(/\.?0+$/, "")} ${unit}`;
}

function statusLabel(status: MoveSummary["checks"][number]["status"]): string {
  return status === "pass" ? "Pass" : status === "warn" ? "Marginal" : status === "fail" ? "Fail" : "Not evaluated";
}

/**
 * Standalone readable report. The summary values are the same strings the
 * panel shows; this module only lays them out.
 */
export function moveReportHtml(summary: MoveSummary, meta: MoveReportMeta): string {
  const p = meta.request.profile;
  const motion: [string, string][] = [
    ["Distance", summary.motion.distance],
    ["Duration", summary.motion.duration],
    ["Peak requested speed", summary.motion.peakSpeed],
    ["Peak requested acceleration", summary.motion.peakAcceleration],
    ["Peak motor force", summary.motion.peakForce],
    ["Moving mass", signed(p.moving_mass_kg * 1000, "g")],
    ["Sliding friction", signed(p.coulomb_friction_n, "N")],
    ["External load", signed(p.external_load_n, "N")],
    ["Viscous damping", signed(p.damping_n_s_per_m, "N·s/m")],
    ["Source", meta.request.source.accepts_regeneration ? "Stiff 12 V link, accepts returned energy" : "Stiff 12 V link, cannot absorb returned energy"],
  ];
  const electrical: [string, string][] = [
    ["Phase peak, no ripple", summary.electrical.phasePeak],
    ["Phase peak including declared ripple", summary.electrical.phasePeakIncludingRipple ?? "Not modelled"],
  ];
  const table = (caption: string, entries: [string, string][]) => `
    <section>
      <h2>${escape(caption)}</h2>
      <table>
        <tbody>${entries.map(([k, v]) => `<tr><th scope="row">${escape(k)}</th><td>${escape(v)}</td></tr>`).join("")}</tbody>
      </table>
    </section>`;

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escape(`${meta.designName} move power report`)}</title>
<style>
  :root { color-scheme: light; }
  body { margin: 0; background: #f4f5f7; color: #16202e; font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 880px; margin: 0 auto; padding: 40px 28px 64px; }
  header { border-bottom: 2px solid #1f6f5c; padding-bottom: 18px; margin-bottom: 26px; }
  .scope { display: inline-block; background: #fdf3d8; color: #6b4d00; border: 1px solid #e5c76b; border-radius: 3px; padding: 2px 8px; font-size: 12px; font-weight: 600; }
  h1 { font-size: 26px; line-height: 1.2; margin: 10px 0 6px; }
  h2 { font-size: 13px; letter-spacing: .02em; margin: 30px 0 8px; color: #43546a; font-weight: 650; }
  p { margin: 0 0 10px; }
  .lede { color: #4a5b70; max-width: 62ch; }
  .headline { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin: 18px 0 4px; }
  .headline div { background: #fff; border: 1px solid #d7dce3; border-radius: 4px; padding: 14px 16px; }
  .headline strong { display: block; font-size: 24px; font-variant-numeric: tabular-nums; letter-spacing: -.01em; }
  .headline span { color: #5c6b7f; font-size: 12px; }
  table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d7dce3; }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #e7eaee; vertical-align: top; }
  tr:last-child th, tr:last-child td { border-bottom: 0; }
  th { font-weight: 500; color: #4a5b70; width: 42%; }
  td { font-variant-numeric: tabular-nums; }
  .checks td:first-child { width: 34%; }
  .status { font-weight: 600; }
  .status-pass { color: #1d6b47; }
  .status-warn { color: #8a5a00; }
  .status-fail { color: #a32424; }
  .status-unknown { color: #5c6b7f; }
  ul { margin: 0; padding-left: 20px; }
  li { margin: 3px 0; }
  .caveat { border-left: 3px solid #d9a520; background: #fffaf0; padding: 10px 14px; margin: 14px 0; }
  footer { margin-top: 38px; border-top: 1px solid #d7dce3; padding-top: 14px; color: #5c6b7f; font-size: 12px; }
  code { font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; overflow-wrap: anywhere; }
  @media print { body { background: #fff; } main { padding: 0; } .headline div, table { break-inside: avoid; } }
</style>
</head>
<body>
<main>
<header>
  <span class="scope">${escape(summary.scope)}</span>
  <h1>${escape(meta.designName)} move power report</h1>
  <p class="lede">${escape(summary.scopeText)}</p>
</header>

<div class="headline">
  <div><strong>${escape(summary.headline.peakPower)}</strong><span>Peak supply draw, estimated</span></div>
  <div><strong>${escape(summary.headline.averagePower)}</strong><span>Average during the move</span></div>
  <div><strong>${escape(summary.headline.energy)}</strong><span>Energy per move</span></div>
  <div><strong>${escape(summary.headline.peakSupplyCurrent)}</strong><span>Peak supply current at ${escape(`${meta.supplyVoltageV} V`)}</span></div>
</div>

${table("Move and load", motion)}
${table("Electrical", electrical)}
<p>${escape(summary.electrical.phaseCurrentVersusSupply)}</p>

<section>
  <h2>Findings</h2>
  <table class="checks">
    <tbody>${summary.checks.map(c => `<tr><th scope="row">${escape(c.label)}<br><span class="status status-${c.status}">${escape(statusLabel(c.status))}</span></th><td>${escape(c.reading)}<br><span>${escape(c.detail)}</span></td></tr>`).join("")}</tbody>
  </table>
</section>

${summary.exclusions.length ? `<section><h2>Analysis-only exclusions</h2><div class="caveat"><ul>${summary.exclusions.map(x => `<li>${escape(x)}</li>`).join("")}</ul><p>These parts remain in the saved design and are not included in this estimate.</p></div></section>` : ""}

<section>
  <h2>Not included</h2>
  <ul>${summary.omissions.map(x => `<li>${escape(x)}</li>`).join("")}</ul>
</section>

<section>
  <h2>Model and design identity</h2>
  <table>
    <tbody>
      <tr><th scope="row">Design</th><td>${escape(meta.designName)}</td></tr>
      <tr><th scope="row">Geometry</th><td>${escape(meta.geometrySource)}</td></tr>
      <tr><th scope="row">Driver</th><td>${escape(`${meta.driverName}, ${meta.pwmHz / 1000} kHz, ${meta.supplyVoltageV} V`)}</td></tr>
      <tr><th scope="row">Assumed winding temperature</th><td>${escape(`${meta.windingTempC} °C`)}</td></tr>
      <tr><th scope="row">Controller</th><td>Balanced star sine, electrical reference ${escape(meta.request.electrical_angle_at_zero_rad.toFixed(6))} rad</td></tr>
      <tr><th scope="row">Motion profile</th><td>Imposed quintic, ${signed(p.initial_velocity_m_s, "m/s")} to ${signed(p.final_velocity_m_s, "m/s")} endpoints</td></tr>
      <tr><th scope="row">Sampling</th><td>${escape(`${meta.request.force_positions} force-map positions, ${p.time_step_s * 1000} ms step`)}</td></tr>
      <tr><th scope="row">Native model</th><td><code>${escape(meta.modelVersion)}</code></td></tr>
      <tr><th scope="row">Input SHA-256</th><td><code>${escape(meta.inputSha256)}</code></td></tr>
      <tr><th scope="row">Generated</th><td>${escape(meta.generatedAt)} by pcbmotorgen ${escape(meta.appVersion)}</td></tr>
    </tbody>
  </table>
</section>

${summary.lossReferences.length ? `<section><h2>Estimates and references</h2><ul>${summary.lossReferences.map(x => `<li>${escape(x)}</li>`).join("")}</ul></section>` : ""}

<footer>
  <p>Imposed-motion demand from the active geometry. The samples are PWM-cycle averages, not achieved motion, measured hardware consumption, a thermal rating or a guaranteed maximum. Negative values would indicate returned energy. Unknown values are unavailable, not zero.</p>
</footer>
</main>
</body>
</html>
`;
}

export function moveReportMarkdown(summary: MoveSummary, meta: MoveReportMeta): string {
  const p = meta.request.profile;
  const line = (k: string, v: string) => `| ${k} | ${v.replaceAll("|", "\\|")} |`;
  const section = (title: string, entries: [string, string][]) => `## ${title}\n\n| Item | Value |\n| --- | --- |\n${entries.map(([k, v]) => line(k, v)).join("\n")}`;
  return `# ${meta.designName} move power report\n\n**${summary.scope}.** ${summary.scopeText}\n\n`
    + section("Move and load", [
      ["Distance", summary.motion.distance],
      ["Duration", summary.motion.duration],
      ["Peak requested speed", summary.motion.peakSpeed],
      ["Peak requested acceleration", summary.motion.peakAcceleration],
      ["Moving mass", signed(p.moving_mass_kg * 1000, "g")],
      ["Sliding friction", signed(p.coulomb_friction_n, "N")],
      ["External load", signed(p.external_load_n, "N")],
      ["Source", meta.request.source.accepts_regeneration ? "Stiff DC link, accepts returned energy" : "Stiff DC link, cannot absorb returned energy"],
    ]) + "\n\n"
    + section("Power", [
      ["Peak supply power", summary.headline.peakPower],
      ["Average power during the move", summary.headline.averagePower],
      ["Energy per move", summary.headline.energy],
      ["Peak supply current", summary.headline.peakSupplyCurrent],
      ["Phase peak, no ripple", summary.electrical.phasePeak],
      ["Phase peak including declared ripple", summary.electrical.phasePeakIncludingRipple ?? "Not modelled"],
    ]) + "\n\n"
    + `## Findings\n\n${summary.checks.map(c => `- **${c.label}** (${statusLabel(c.status)}): ${c.reading}. ${c.detail}`).join("\n")}\n\n`
    + (summary.exclusions.length ? `## Analysis-only exclusions\n\n${summary.exclusions.map(x => `- ${x}`).join("\n")}\n\nThese parts remain in the saved design.\n\n` : "")
    + `## Not included\n\n${summary.omissions.map(x => `- ${x}`).join("\n")}\n\n`
    + section("Model and design identity", [
      ["Design", meta.designName],
      ["Geometry", meta.geometrySource],
      ["Driver", `${meta.driverName}, ${meta.pwmHz / 1000} kHz, ${meta.supplyVoltageV} V`],
      ["Winding temperature", `${meta.windingTempC} °C`],
      ["Native model", meta.modelVersion],
      ["Input SHA-256", meta.inputSha256],
      ["Generated", `${meta.generatedAt} by pcbmotorgen ${meta.appVersion}`],
    ]) + "\n\n"
    + (summary.lossReferences.length ? `## Estimates and references\n\n${summary.lossReferences.map(x => `- ${x}`).join("\n")}\n\n` : "")
    + "Imposed-motion demand from the active geometry. Not achieved motion, measured consumption or a guaranteed maximum.\n";
}
