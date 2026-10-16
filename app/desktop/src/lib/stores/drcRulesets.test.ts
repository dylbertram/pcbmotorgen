import { afterEach, describe, expect, it, vi } from "vitest";
import { DrcRulesets } from "./drcRulesets.svelte";
import { DEFAULT_RULES } from "../preferences";

afterEach(() => vi.unstubAllGlobals());

function memoryStorage() {
  let saved: string | null = null;
  return {
    storage: {
      getItem: () => saved,
      setItem: (_key: string, value: string) => { saved = value; },
    },
    get value() { return saved; },
  };
}

describe("drc rulesets store", () => {
  it("saves named snapshots, rejects duplicates, and deletes", () => {
    const memory = memoryStorage();
    vi.stubGlobal("localStorage", memory.storage);
    const store = new DrcRulesets();
    expect(store.rulesets).toEqual([]);

    expect(store.add("  1 oz  ", { ...DEFAULT_RULES, min_space_mm: 0.2 })).toBeNull();
    expect(store.rulesets).toEqual([{ name: "1 oz", rules: { ...DEFAULT_RULES, min_space_mm: 0.2 } }]);
    expect(memory.value).toContain("1 oz");

    // Names are compared case-insensitively after trimming.
    expect(store.add("1 OZ", DEFAULT_RULES)).toMatch(/already exists/i);
    expect(store.rulesets).toHaveLength(1);

    expect(store.add("", DEFAULT_RULES)).toMatch(/name/i);
    expect(store.rulesets).toHaveLength(1);

    store.remove(0);
    expect(store.rulesets).toEqual([]);
    expect(memory.value).toBe("[]");
  });

  it("flags unavailable storage without dropping the in-memory list", () => {
    vi.stubGlobal("localStorage", { getItem() { throw new Error("nope"); }, setItem() { throw new Error("nope"); } });
    const store = new DrcRulesets();
    expect(store.add("1 oz", DEFAULT_RULES)).toBeNull();
    expect(store.storageAvailable).toBe(false);
    expect(store.rulesets.map((entry) => entry.name)).toEqual(["1 oz"]);
  });
});
