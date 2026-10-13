import type { DrcRules } from "./preferences";

type Expression = string | Expression[];
export interface ImportedDrcRules {
  rules: Partial<DrcRules>;
  warnings: string[];
}

// KiCad rules are S-expressions. Comments and quoted conditions must be
// tokenized before looking for constraints, not searched with a file-wide regex.
function parse(text: string): Expression[][] {
  const roots: Expression[][] = [];
  const stack: Expression[][] = [];
  let index = text.charCodeAt(0) === 0xfeff ? 1 : 0;
  while (index < text.length) {
    const char = text[index];
    if (/\s/.test(char)) { index++; continue; }
    if (char === "#") {
      while (index < text.length && text[index] !== "\n") index++;
      continue;
    }
    if (char === "(") {
      const node: Expression[] = [];
      if (stack.length) stack[stack.length - 1].push(node);
      else roots.push(node);
      stack.push(node);
      index++;
      continue;
    }
    if (char === ")") {
      if (!stack.pop()) throw new Error("Unexpected closing parenthesis in KiCad rules.");
      index++;
      continue;
    }
    if (!stack.length) throw new Error("Expected a KiCad rule expression.");
    let token = "";
    if (char === '"') {
      index++;
      while (index < text.length && text[index] !== '"') {
        if (text[index] === "\\") {
          index++;
          if (index >= text.length) break;
        }
        token += text[index++];
      }
      if (text[index] !== '"') throw new Error("Unterminated string in KiCad rules.");
      index++;
    } else {
      while (index < text.length && !/[\s()#]/.test(text[index])) token += text[index++];
    }
    stack[stack.length - 1].push(token);
  }
  if (stack.length) throw new Error("Unclosed parenthesis in KiCad rules.");
  if (roots[0]?.length !== 2 || roots[0][0] !== "version" || roots[0][1] !== "1") {
    throw new Error("Expected a KiCad .kicad_dru file with (version 1).");
  }
  return roots.slice(1);
}

function millimeters(value: Expression | undefined): number {
  if (typeof value !== "string") throw new Error("Missing minimum constraint value.");
  const match = /^([+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)\s*(mm|mil|in)?$/i.exec(value);
  if (!match) throw new Error(`Unsupported minimum value: ${value}. Use mm, mil, or in.`);
  const result = Number(match[1]) * (match[2]?.toLowerCase() === "mil" ? 0.0254 : match[2]?.toLowerCase() === "in" ? 25.4 : 1);
  if (!Number.isFinite(result) || result <= 0) throw new Error("Minimum constraint values must be positive.");
  return result;
}

/** Import a conservative, uniform subset, not KiCad's conditional rule engine. */
export function importKicadDrc(text: string, current: DrcRules): ImportedDrcRules {
  const rules: Partial<DrcRules> = {};
  const warnings = new Set<string>();
  const diameters: number[] = [];
  const setMinimum = (key: keyof DrcRules, value: number) => {
    rules[key] = Math.max(rules[key] ?? 0, value);
  };
  for (const rule of parse(text)) {
    if (rule[0] !== "rule" || typeof rule[1] !== "string") throw new Error("Invalid KiCad rule expression.");
    const name = rule[1];
    const entries = rule.slice(2);
    if (entries.some(entry => !Array.isArray(entry))) throw new Error(`Invalid rule: ${name}.`);
    const clauses = entries as Expression[][];
    const conditions = clauses.filter(entry => entry[0] === "condition");
    const condition = conditions[0]?.[1];
    const type = typeof condition === "string" ? /^\s*A\.Type\s*==\s*'(track|via)'\s*$/i.exec(condition)?.[1].toLowerCase() : undefined;
    if (conditions.length > 1 || (conditions.length && !type) || clauses.some(entry => entry[0] === "severity" && entry[1] === "ignore")) {
      warnings.add(`Skipped conditional or disabled rule "${name}".`);
      continue;
    }
    if (clauses.some(entry => entry[0] === "layer")) {
      warnings.add("Layer-specific minima are applied to all motor layers.");
    }
    for (const clause of clauses) {
      if (clause[0] !== "constraint") continue;
      const kind = clause[1];
      const key = kind === "track_width" && type !== "via" ? "min_trace_mm"
        : kind === "clearance" ? "min_space_mm"
        : kind === "hole_size" && type !== "track" ? "min_via_drill_mm"
        : kind === "annular_width" && type !== "track" ? "min_via_annular_ring_mm"
        : undefined;
      const diameter = kind === "via_diameter" && type !== "track";
      if (!key && !diameter) {
        warnings.add(`Unsupported constraint "${String(kind)}" in "${name}".`);
        continue;
      }
      const min = clause.find(entry => Array.isArray(entry) && entry[0] === "min") as Expression[] | undefined;
      if (!min) { warnings.add(`No minimum for "${String(kind)}" in "${name}".`); continue; }
      const value = millimeters(min[1]);
      if (key) setMinimum(key, value);
      else diameters.push(value);
      if (clause.some(entry => Array.isArray(entry) && entry[0] !== "min")) {
        warnings.add("Maximum and preferred constraint values are not imported.");
      }
    }
  }
  if (diameters.length) {
    const drill = rules.min_via_drill_mm ?? current.min_via_drill_mm;
    if (!Number.isFinite(drill) || drill <= 0) throw new Error("Enter a positive minimum via drill before importing a diameter-only rule.");
    const ring = (Math.max(...diameters) - drill) / 2;
    if (ring > 0) setMinimum("min_via_annular_ring_mm", Number(ring.toPrecision(12)));
    warnings.add("Via diameter is converted to annular ring width using the imported or current minimum drill. The app does not retain a separate diameter limit.");
  }
  if (!Object.keys(rules).length) throw new Error("No supported minimum motor rules found in this file.");
  warnings.add("The strictest imported minimum is used for each field. Conditional KiCad rule precedence is not reproduced. Unchanged fields keep their current values.");
  return { rules, warnings: [...warnings] };
}
