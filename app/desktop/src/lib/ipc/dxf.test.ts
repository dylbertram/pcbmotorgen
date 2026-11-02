import { beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { ConfigStore } from "../stores/config.svelte";
import type { CadGeometry } from "../types";
import { editableCoilGeometry, exportCadGeometryDxf, exportCoilsDxf, importCadDxf, pickCadDxfPath } from "./dxf";

const runtime = vi.hoisted(() => ({ available: false }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./core", async (original) => ({ ...await original<typeof import("./core")>(), isTauriAvailable: () => runtime.available }));

beforeEach(() => {
  runtime.available = false;
  vi.mocked(invoke).mockReset();
});

describe("DXF browser boundary", () => {
  it("exports only a clearly marked placeholder for generated coils", async () => {
    const config = new ConfigStore().toIpc();
    const result = await exportCoilsDxf(config);
    expect(result.dxf_content).toContain("SECTION");
    expect(result.dxf_content).toContain("EOF");
    expect(result.dxf_content).toContain("Mock DXF — backend not connected");
    expect(result.summary).toEqual({ total_lines: 0, total_arcs: 0, total_circles: 0, layer_count: 1 });
    expect(invoke).not.toHaveBeenCalled();
  });

  it("does not fabricate CAD import, editable geometry or CAD exports", async () => {
    await expect(pickCadDxfPath()).rejects.toThrow("CAD import requires the desktop app");
    await expect(importCadDxf("test.dxf", 1, 0.01, 0.2, 2, 1.6)).rejects.toThrow("CAD import requires the desktop app");
    await expect(editableCoilGeometry(new ConfigStore().toIpc())).rejects.toThrow("Editing generated segments requires the desktop app");
    await expect(exportCadGeometryDxf({} as CadGeometry)).rejects.toThrow("CAD export requires the desktop app");
    expect(invoke).not.toHaveBeenCalled();
  });
});

it("uses the native command and propagates its errors when the backend is available", async () => {
  runtime.available = true;
  const config = new ConfigStore().toIpc();
  vi.mocked(invoke).mockRejectedValueOnce(new Error("native export failed"));
  await expect(exportCoilsDxf(config)).rejects.toThrow("native export failed");
  expect(invoke).toHaveBeenCalledWith("export_coils_dxf", { config });
});
