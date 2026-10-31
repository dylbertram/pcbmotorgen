import { describe, expect, it } from "vitest";
import { ConfigStore } from "./config.svelte";
import { listRoutingPatterns } from "../ipc/routing";

describe("routing source connection metadata", () => {
  it("keeps fresh projects star while old absent parameters remain closed", async () => {
    const store = new ConfigStore();
    store.routing_patterns = await listRoutingPatterns();
    expect(store.generatorConnection).toBe("star");
    store.routing_params = {};
    expect(store.generatorConnection).toBe("closed");
    await store.loadRoutingParams("infinity-braid");
    expect(store.generatorConnection).toBe("closed");
    expect(store.routing_params.connection).toBeUndefined();
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
