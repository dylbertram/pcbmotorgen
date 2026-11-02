import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConfigStore } from "../stores/config.svelte";
import { mockBoardDiagnostics } from "./kicadMocks";

const { invoke, available } = vi.hoisted(() => ({ invoke: vi.fn(), available: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("./core", () => ({ isTauriAvailable: available }));

import { validateWritePreconditions } from "./kicad";

describe("KiCad precondition IPC", () => {
  beforeEach(() => vi.resetAllMocks());

  it("returns the existing empty preview result without invoking a native check in a browser", async () => {
    available.mockReturnValue(false);
    const config = new ConfigStore().toIpc();
    await expect(validateWritePreconditions(config, mockBoardDiagnostics())).resolves.toEqual([]);
    expect(invoke).not.toHaveBeenCalled();
  });

  it("passes native validation inputs through and propagates failures", async () => {
    available.mockReturnValue(true);
    const config = new ConfigStore().toIpc();
    const diagnostics = mockBoardDiagnostics();
    invoke.mockRejectedValue(new Error("board check failed"));
    await expect(validateWritePreconditions(config, diagnostics)).rejects.toThrow("board check failed");
    expect(invoke).toHaveBeenCalledWith("validate_write_preconditions", { config, diagnostics, cadGeometry: null });
  });
});
