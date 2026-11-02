import { beforeEach, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { ConfigStore } from "../stores/config.svelte";
import type { MovePowerInputs } from "../types/movePower";
import { isTauriAvailable } from "./core";
import { cancelMovePower, evaluateMovePower } from "./movePower";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./core", async (original) => ({
  ...await original<typeof import("./core")>(),
  isTauriAvailable: vi.fn(),
}));

// Only the IPC gate fields are used by these boundary tests.
const inputs = () => ({ topology: "linear", config: new ConfigStore().toIpc(), cad_geometry: null }) as MovePowerInputs;

beforeEach(() => { vi.resetAllMocks(); });

it("does not fabricate browser move results or invoke native cancellation", async () => {
  vi.mocked(isTauriAvailable).mockReturnValue(false);
  await expect(evaluateMovePower("move-1", inputs())).rejects.toThrow("requires the desktop app");
  await expect(cancelMovePower("move-1")).resolves.toBe(false);
  expect(invoke).not.toHaveBeenCalled();
});

it("rejects non-linear requests before invoking native code", async () => {
  vi.mocked(isTauriAvailable).mockReturnValue(true);
  await expect(evaluateMovePower("move-1", { ...inputs(), topology: "radial" })).rejects.toThrow("one linear track");
  expect(invoke).not.toHaveBeenCalled();
});

it("rejects imported copper without explicit terminals before native execution", async () => {
  vi.mocked(isTauriAvailable).mockReturnValue(true);
  const request = inputs();
  request.cad_geometry = {
    layer_z_mm: [0], trace_width_mm: 0.2, coil_terminals: {},
    routing: { format_version: 2, curves: [], vias: [], segments: [
      { start: { x: 0, y: 0 }, end: { x: 1, y: 0 }, layer: 0, net: "A", is_active: false },
    ] },
  };
  await expect(evaluateMovePower("move-1", request)).rejects.toThrow("Select driver and opposite ends");
  expect(invoke).not.toHaveBeenCalled();
});

it("forwards native requests and propagates failures", async () => {
  vi.mocked(isTauriAvailable).mockReturnValue(true);
  const request = inputs();
  vi.mocked(invoke).mockRejectedValueOnce(new Error("native move failed"));
  await expect(evaluateMovePower("move-1", request)).rejects.toThrow("native move failed");
  expect(invoke).toHaveBeenCalledWith("evaluate_move_power", { requestId: "move-1", inputs: request });
  vi.mocked(invoke).mockResolvedValueOnce(true);
  await expect(cancelMovePower("move-1")).resolves.toBe(true);
  expect(invoke).toHaveBeenLastCalledWith("cancel_move_power", { requestId: "move-1" });
});
