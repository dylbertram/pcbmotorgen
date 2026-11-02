import { expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { ConfigStore } from "../stores/config.svelte";
import { checkCoilInterference } from "./drc";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./core", async (original) => ({
  ...await original<typeof import("./core")>(),
  isTauriAvailable: () => false,
}));

it("keeps the browser-only empty interference fallback without invoking native code", async () => {
  await expect(checkCoilInterference(new ConfigStore().toIpc())).resolves.toEqual([]);
  expect(invoke).not.toHaveBeenCalled();
});

it("checks imported terminal mapping before returning the browser fallback", async () => {
  const config = new ConfigStore();
  config.phases = 1;
  const geometry = {
    layer_z_mm: [0], trace_width_mm: 0.2, coil_terminals: {},
    routing: { format_version: 2, curves: [], vias: [], segments: [
      { start: { x: 0, y: 0 }, end: { x: 1, y: 0 }, layer: 0, net: "A", is_active: false },
    ] },
  };
  await expect(checkCoilInterference(config.toIpc(), geometry)).rejects.toThrow("Select driver and opposite ends");
  expect(invoke).not.toHaveBeenCalled();
});
