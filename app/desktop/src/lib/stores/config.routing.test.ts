import { describe, expect, it } from "vitest";
import { ConfigStore } from "./config.svelte";
import { listRoutingPatterns, routingPatternParameters } from "../ipc/routing";

describe("routing source connection metadata", () => {
  it("constrains electrical pitch against the actual magnet length without resizing it", () => {
    const store = new ConfigStore();
    store.magnet_width_mm = 5;
    expect(store.min_electrical_pitch_mm).toBe(10);
    expect(store.max_electrical_pitch_mm).toBe(20);
    store.electrical_pitch_mm = 9;
    expect(store.max_magnet_width_mm).toBe(4.5);
    expect(store.magnet_width_mm).toBe(5);
    expect(store.toIpc().magnet_pitch_m).toBe(0.0045);
  });
  it("keeps an explicit legacy zero when loading parameter definitions", async () => {
    const store = new ConfigStore();
    store.routing_patterns = await listRoutingPatterns();
    store.routing_params = { connection: 0, num_strands: 3 };
    await store.loadRoutingParams("infinity-braid");
    expect(store.generatorConnection).toBe("closed");
    expect(store.toIpc().routing_params.connection).toBe(0);
    const connection = (await routingPatternParameters("infinity-braid")).find(def => def.key === "connection")!;
    expect(connection.min).toBe(0);
    expect(connection.options).toContainEqual({ value: 0, label: "Closed (legacy)" });
  });
  it("keeps fresh projects star while old absent parameters remain closed", async () => {
    const store = new ConfigStore();
    store.routing_patterns = await listRoutingPatterns();
    expect(store.generatorConnection).toBe("star");
    expect(store.routing_params.pole_matched).toBe(1);
    store.routing_params = {};
    expect(store.generatorConnection).toBe("closed");
    await store.loadRoutingParams("infinity-braid");
    expect(store.generatorConnection).toBe("closed");
    expect(store.routing_params.connection).toBeUndefined();
    expect(store.routing_params.pole_matched).toBe(0);
  });
  it("persists original IDs and values when changing a source variant", async () => {
    const store = new ConfigStore();
    store.routing_patterns = await listRoutingPatterns();
    store.routing_params = { connection: 2, num_strands: 5 };
    const version = store.routing_params_version;
    store.setRoutingParam("connection", 1);
    expect(store.generatorConnection).toBe("delta");
    expect(store.routing_params_version).toBeGreaterThan(version);
    expect(store.toIpc().routing_pattern).toBe("infinity-braid");
    expect(store.toIpc().routing_params).toEqual({ connection: 1, num_strands: 5 });
    expect(store.toIpc().num_layers).toBe(4);
  });
});
