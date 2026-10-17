import { validRules, type DrcRules } from "./preferences";

/**
 * Named, persisted DRC rulesets for the Settings dialog.
 *
 * Each entry is a snapshot of the four design rules the user can save and
 * reload later. They live in their own storage key so the active defaults in
 * `preferences.ts` keep their existing shape; the selected ruleset is copied
 * into the dialog's draft and only becomes active when the user saves.
 */
export interface DrcRuleset {
  name: string;
  rules: DrcRules;
}

const STORAGE_KEY = "pcbmotorgen.drc_rulesets.v1";

/** Return the first problem with a ruleset, or null when it can be saved. */
export function rulesetValidationError(ruleset: DrcRuleset): string | null {
  if (typeof ruleset.name !== "string" || !ruleset.name.trim()) return "Enter a ruleset name.";
  if (!ruleset.rules || !validRules(ruleset.rules)) return "Every rule must be a positive number.";
  return null;
}

/** Parse a stored list, dropping malformed entries. Null/garbage -> empty. */
function parseStored(raw: string | null): DrcRuleset[] {
  try {
    const saved: unknown = JSON.parse(raw ?? "null");
    if (!Array.isArray(saved)) return [];
    return saved.map((entry) => entry && typeof entry === "object" && entry.rules
      ? { ...entry, rules: { ...entry.rules, trace_width_mm: entry.rules.trace_width_mm ?? entry.rules.min_trace_mm } }
      : entry).filter((ruleset): ruleset is DrcRuleset =>
      ruleset !== null && typeof ruleset === "object" &&
      rulesetValidationError(ruleset as DrcRuleset) === null);
  } catch {
    return [];
  }
}

export function readRulesets(): DrcRuleset[] {
  if (typeof localStorage === "undefined") return [];
  try {
    return parseStored(localStorage.getItem(STORAGE_KEY));
  } catch {
    return [];
  }
}

/** Return false when browser storage is unavailable; the in-memory list survives. */
export function saveRulesets(rulesets: DrcRuleset[]): boolean {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(rulesets));
    return true;
  } catch {
    return false;
  }
}
