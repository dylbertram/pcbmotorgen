import { describe, expect, it } from "vitest";
import { ConfigStore } from "../stores/config.svelte";
import {
  mockBoardDiagnostics,
  mockKicadConnection,
  mockKicadWrite,
  mockPreviewCoils,
} from "./kicadMocks";

describe("browser KiCad mocks", () => {
  it("returns a disconnected placeholder board", () => {
    const diagnostics = mockBoardDiagnostics();
    expect(diagnostics.board_name).toContain("mock");
    expect(diagnostics.copper_layer_count).toBeGreaterThan(0);
    expect(diagnostics.available_net_classes).toEqual([]);
  });

  it("reports the offline boundary without pretending a write succeeded", () => {
    expect(mockKicadConnection()).toMatchObject({ connected: false, copper_layers: 0 });
    const result = mockKicadWrite();
    expect(result).toMatchObject({ items_attempted: 0, items_created: 0 });
    expect(result.failures).toContain("Backend not available — open the Tauri shell to write to KiCad");
  });

  it("tallies tracks as conductors and end-turns × phases × layers", () => {
    const config = { ...new ConfigStore().toIpc(), magnet_count: 4, phases: 3, num_layers: 2 };
    const preview = mockPreviewCoils(config);
    expect(preview.num_layers).toBe(2);
    expect(preview.layers).toHaveLength(2);
    expect(preview.total_tracks).toBe(15 * 3 * 2);
    expect(preview.total_vias).toBe(0);
    expect(preview.pattern_id).toBe(config.routing_pattern);
  });
});
