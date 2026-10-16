/**
 * Shared, reactive view of the saved DRC rulesets.
 *
 * The Settings dialog reads and writes this one instance. Validation and
 * persistence stay in `lib/drcRulesets.ts` (pure functions, unit-tested); this
 * store only holds the in-memory list and reports whether a write reached
 * browser storage.
 */
import { readRulesets, rulesetValidationError, saveRulesets, type DrcRuleset } from "../drcRulesets";
import type { DrcRules } from "../preferences";

export class DrcRulesets {
  rulesets = $state<DrcRuleset[]>(readRulesets());
  /** False once a write fails; the rulesets still exist for this session. */
  storageAvailable = $state(true);

  #persist(): void {
    this.storageAvailable = saveRulesets($state.snapshot(this.rulesets));
  }

  /**
   * Save a named snapshot of `rules`. Returns an error message when the name
   * is empty or already used, otherwise null once the list is persisted.
   */
  add(name: string, rules: DrcRules): string | null {
    const trimmed = name.trim();
    const candidate: DrcRuleset = { name: trimmed, rules: { ...rules } };
    const error = rulesetValidationError(candidate);
    if (error) return error;
    if (this.rulesets.some((saved) => saved.name.toLowerCase() === trimmed.toLowerCase()))
      return `A ruleset named "${trimmed}" already exists.`;
    this.rulesets = [...this.rulesets, candidate];
    this.#persist();
    return null;
  }

  remove(index: number): void {
    this.rulesets = this.rulesets.filter((_, i) => i !== index);
    this.#persist();
  }
}

export const drcRulesets = new DrcRulesets();
