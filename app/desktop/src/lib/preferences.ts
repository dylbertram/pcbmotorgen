export type Appearance = "light" | "dark" | "auto";
export interface DrcRules {
  min_trace_mm: number;
  min_space_mm: number;
  min_via_drill_mm: number;
  min_via_annular_ring_mm: number;
}
export interface Preferences {
  appearance: Appearance;
  rules: DrcRules;
}

export const PREFERENCES_KEY = "pcbmotorgen.preferences.v1";
export const DEFAULT_RULES: DrcRules = {
  min_trace_mm: 0.127,
  min_space_mm: 0.127,
  min_via_drill_mm: 0.2,
  min_via_annular_ring_mm: 0.1,
};
export const RULE_FIELDS = [
  { key: "min_trace_mm", label: "Minimum trace width" },
  { key: "min_space_mm", label: "Minimum clearance" },
  { key: "min_via_drill_mm", label: "Minimum via drill" },
  { key: "min_via_annular_ring_mm", label: "Minimum via annular ring" },
] as const;

export function validRules(rules: DrcRules): boolean {
  return RULE_FIELDS.every(({ key }) => Number.isFinite(rules[key]) && rules[key] > 0);
}

export function readPreferences(): Preferences {
  const defaults: Preferences = { appearance: "auto", rules: { ...DEFAULT_RULES } };
  if (typeof window === "undefined") return defaults;
  try {
    const stored = JSON.parse(localStorage.getItem(PREFERENCES_KEY) ?? "null");
    if (!stored || typeof stored !== "object") return defaults;
    if (["light", "dark", "auto"].includes(stored.appearance)) defaults.appearance = stored.appearance;
    if (stored.rules && validRules(stored.rules)) {
      for (const { key } of RULE_FIELDS) defaults.rules[key] = stored.rules[key];
    }
  } catch {
    // Missing, corrupt, or unavailable storage must not prevent startup.
  }
  return defaults;
}

export function writePreferences(preferences: Preferences): void {
  if (!["light", "dark", "auto"].includes(preferences.appearance) || !validRules(preferences.rules)) {
    throw new Error("Choose an appearance and enter a positive value for every DRC rule.");
  }
  // Write before applying changes so a failed save leaves the design untouched.
  localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences));
  applyAppearance(preferences.appearance);
}

export function applyAppearance(appearance: Appearance): void {
  const dark = appearance === "dark" || (appearance === "auto" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
}

/** Apply before mount, and follow OS appearance changes while in Auto mode. */
export function initializeAppearance(): () => void {
  applyAppearance(readPreferences().appearance);
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const update = () => applyAppearance(readPreferences().appearance);
  media.addEventListener("change", update);
  window.addEventListener("storage", update);
  return () => {
    media.removeEventListener("change", update);
    window.removeEventListener("storage", update);
  };
}
