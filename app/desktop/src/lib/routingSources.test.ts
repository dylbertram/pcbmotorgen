import { describe, expect, it } from "vitest";
import { generatorConnection, routingSources } from "./routingSources";
import type { RoutingPatternInfo } from "./types/routing";

const braid: RoutingPatternInfo = { id: "infinity-braid", display_name: "Infinity Braid", end_type: {
  kind: "parameter", key: "connection", default: 0, options: [
    { value: 2, connection: "star" }, { value: 1, connection: "delta" }, { value: 0, connection: "closed" },
  ],
} };

describe("generator-driven routing sources", () => {
  it("offers star and delta without changing persisted IDs or parameters", () => {
    const params = { connection: 2, num_strands: 5 };
    const sources = routingSources([braid], braid.id, params);
    expect(sources.map((source) => source.label)).toEqual(["Infinity Braid - Star (Wye)", "Infinity Braid - Delta"]);
    expect(sources.map((source) => source.patternId)).toEqual([braid.id, braid.id]);
    expect(sources[1].parameter).toEqual({ key: "connection", value: 1 });
    expect(params).toEqual({ connection: 2, num_strands: 5 });
  });
  it("honors missing, closed, and unknown saved values without seeding star", () => {
    expect(generatorConnection(braid.end_type, {})).toBe("closed");
    expect(generatorConnection(braid.end_type, { connection: 0 })).toBe("closed");
    expect(generatorConnection(braid.end_type, { connection: 1 })).toBe("delta");
    expect(generatorConnection(braid.end_type, { connection: 99 })).toBeNull();
    expect(routingSources([braid], braid.id, { connection: 99 }).map((source) => source.label)).toContain("Infinity Braid - Unknown connection (99)");
    expect(routingSources([braid], braid.id, {}).map((source) => source.label)).toContain("Infinity Braid - Closed (legacy)");
  });
  it("supports fixed metadata and generators without metadata", () => {
    const fixed: RoutingPatternInfo = { id: "fixed", display_name: "Fixed", end_type: { kind: "fixed", connection: "delta" } };
    const legacy: RoutingPatternInfo = { id: "legacy", display_name: "Legacy" };
    expect(generatorConnection(fixed.end_type, {})).toBe("delta");
    expect(generatorConnection(legacy.end_type, {})).toBeNull();
    expect(routingSources([fixed, legacy], fixed.id, {})).toEqual([
      { value: fixed.id, label: "Fixed - Delta", patternId: fixed.id, parameter: null },
      { value: legacy.id, label: "Legacy", patternId: legacy.id, parameter: null },
    ]);
  });
});
