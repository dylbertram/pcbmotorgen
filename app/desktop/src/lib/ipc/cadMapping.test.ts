import { afterEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { ConfigStore } from "../stores/config.svelte";
import type { CadGeometry } from "../types";
import { evaluateForceSweep, analyzeDrive } from "./physics";
import { checkCoilInterference } from "./routing";
import { previewCoils, validateWritePreconditions, writeCoilsToBoard } from "./kicad";
import { mockBoardDiagnostics } from "./mocks";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn().mockResolvedValue({}) }));
vi.mock("./core", async (original) => ({ ...await original<typeof import("./core")>(), isTauriAvailable: () => true }));
afterEach(() => vi.clearAllMocks());

function geometry(): CadGeometry {
  return { motor_mapping_reviewed: true, layer_z_mm: [0], trace_width_mm: 0.2,
    coil_terminals: { A: { input: { position: { x: 0, y: 0 }, layer: 0 }, output: { position: { x: 1, y: 0 }, layer: 0 } } },
    routing: { format_version: 2, curves: [], vias: [], segments: [
      { start: { x: 0, y: 0 }, end: { x: 1, y: 0 }, layer: 0, net: "A", is_active: false },
    ] },
  };
}

describe("import mapping IPC gates", () => {
  it("does not apply star equations to an imported delta winding", async () => {
    const config = new ConfigStore(); config.phases = 1;
    const g = geometry(); g.terminal_connection = "delta";
    await expect(evaluateForceSweep(config.toIpc(), g, config.drive)).rejects.toThrow("delta force analysis");
    await expect(analyzeDrive(config.toIpc(), config.drive, null, g)).rejects.toThrow("Star (wye)");
    expect(invoke).not.toHaveBeenCalled();
  });
  it("blocks every motor workflow before invoking the backend for an incomplete import", async () => {
    const config = new ConfigStore(); config.phases = 1;
    const ipc = config.toIpc();
    const g = geometry(); g.motor_mapping_reviewed = false;
    const calls = [
      () => evaluateForceSweep(ipc, g, config.drive),
      () => analyzeDrive(ipc, config.drive, null, g),
      () => checkCoilInterference(ipc, g),
      () => previewCoils(ipc, g),
      () => validateWritePreconditions(ipc, mockBoardDiagnostics(), g),
      () => writeCoilsToBoard(ipc, false, g),
    ];
    for (const call of calls) await expect(call()).rejects.toThrow("Review conductor roles");
    expect(invoke).not.toHaveBeenCalled();
  });

  it("passes reviewed imported copper and its roles unchanged to each backend workflow", async () => {
    const config = new ConfigStore(); config.phases = 1;
    const ipc = config.toIpc(), g = geometry();
    await evaluateForceSweep(ipc, g, config.drive);
    await analyzeDrive(ipc, config.drive, null, g);
    await checkCoilInterference(ipc, g);
    await previewCoils(ipc, g);
    await writeCoilsToBoard(ipc, true, g);
    expect(vi.mocked(invoke).mock.calls.map(([command]) => command)).toEqual([
      "evaluate_force_sweep", "analyze_drive", "check_coil_interference", "preview_coils", "write_coils_to_board",
    ]);
    for (const [, args] of vi.mocked(invoke).mock.calls) expect(args).toMatchObject({ cadGeometry: g });
  });
});
