import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_RULES, PREFERENCES_KEY, applyAppearance, initializeAppearance, readPreferences, validRules, writePreferences } from "./preferences";
import { ConfigStore } from "./stores/config.svelte";
import { ProjectStore } from "./stores/project.svelte";
import { MotionStore } from "./stores/motion.svelte";

describe("preferences", () => {
  let values: Map<string, string>;
  let root: { dataset: Record<string, string>; style: Record<string, string> };
  let media: { matches: boolean; addEventListener: ReturnType<typeof vi.fn>; removeEventListener: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    values = new Map();
    root = { dataset: {}, style: {} };
    media = { matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() };
    vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value) });
    vi.stubGlobal("window", { matchMedia: () => media, addEventListener: vi.fn(), removeEventListener: vi.fn() });
    vi.stubGlobal("document", { documentElement: root });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("uses Auto and manufacturer defaults without saved settings", () => {
    expect(readPreferences()).toEqual({ appearance: "auto", rules: DEFAULT_RULES });
  });

  it("recovers from corrupt and invalid preferences", () => {
    for (const value of ["{bad", "null", JSON.stringify({ appearance: "sepia", rules: { ...DEFAULT_RULES, min_trace_mm: -1 } })]) {
      values.set(PREFERENCES_KEY, value);
      expect(readPreferences()).toEqual({ appearance: "auto", rules: DEFAULT_RULES });
    }
    vi.stubGlobal("localStorage", { getItem: () => { throw new Error("Unavailable"); } });
    expect(readPreferences().rules).toEqual(DEFAULT_RULES);
  });

  it("persists preferences and initializes new config stores with saved rules", () => {
    const rules = { ...DEFAULT_RULES, min_space_mm: 0.3 };
    writePreferences({ appearance: "dark", rules });
    expect(readPreferences()).toEqual({ appearance: "dark", rules });
    expect(new ConfigStore().min_space_mm).toBe(0.3);
    expect(root.dataset.theme).toBe("dark");
  });

  it("rejects empty, non-finite, zero, and negative rule values", () => {
    for (const value of [undefined, NaN, Infinity, 0, -1]) {
      expect(validRules({ ...DEFAULT_RULES, min_trace_mm: value as number })).toBe(false);
    }
    expect(() => writePreferences({ appearance: "auto", rules: { ...DEFAULT_RULES, min_space_mm: 0 } })).toThrow();
    expect(values.size).toBe(0);
  });

  it("project restoration retains saved rules while New uses updated defaults", async () => {
    const config = new ConfigStore();
    vi.spyOn(config, "loadRoutingParams").mockResolvedValue(undefined);
    const projects = new ProjectStore(config, new MotionStore(config));
    const saved = projects.snapshotIpc();
    writePreferences({ appearance: "auto", rules: { ...DEFAULT_RULES, min_space_mm: 0.3 } });
    projects.applyToState(saved);
    expect(config.min_space_mm).toBe(0.127);
    projects.markClean();
    expect(await projects.newProject()).toBe(true);
    expect(config.min_space_mm).toBe(0.3);
    expect(projects.isDirty).toBe(false);
  });

  it("does not apply appearance if storage fails", () => {
    applyAppearance("dark");
    vi.stubGlobal("localStorage", { setItem: () => { throw new Error("Disk full"); } });
    expect(() => writePreferences({ appearance: "light", rules: DEFAULT_RULES })).toThrow("Disk full");
    expect(root.dataset.theme).toBe("dark");
  });

  it("follows system changes in Auto but respects explicit appearance", () => {
    const dispose = initializeAppearance();
    expect(root.dataset.theme).toBe("light");
    const update = media.addEventListener.mock.calls[0][1];
    media.matches = true;
    update();
    expect(root.dataset.theme).toBe("dark");
    writePreferences({ appearance: "light", rules: DEFAULT_RULES });
    update();
    expect(root.dataset.theme).toBe("light");
    dispose();
    expect(media.removeEventListener).toHaveBeenCalledWith("change", update);
  });
});
