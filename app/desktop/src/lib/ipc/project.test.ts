import { beforeEach, describe, expect, it, vi } from "vitest";
import { listen } from "@tauri-apps/api/event";
import { isTauriAvailable } from "./core";
import { bindProjectMenuActions } from "./project";

vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
vi.mock("./core", () => ({ isTauriAvailable: vi.fn() }));

describe("native File menu actions", () => {
  beforeEach(() => vi.clearAllMocks());

  it("dispatches New, DXF, and KiCad events and removes all listeners", async () => {
    vi.mocked(isTauriAvailable).mockReturnValue(true);
    const unlisten = vi.fn();
    vi.mocked(listen).mockResolvedValue(unlisten);
    const handlers = {
      newProject: vi.fn(), exportDxf: vi.fn(), sendKicad: vi.fn(),
      open: vi.fn(), save: vi.fn(), saveAs: vi.fn(), saveNewVersion: vi.fn(), settings: vi.fn(),
    };
    const unbind = await bindProjectMenuActions(handlers);
    for (const [eventName, handler] of [
      ["menu:new-project", handlers.newProject],
      ["menu:export-dxf", handlers.exportDxf],
      ["menu:send-kicad", handlers.sendKicad],
      ["menu:save-project-new-version", handlers.saveNewVersion],
      ["menu:settings", handlers.settings],
    ] as const) {
      const registration = vi.mocked(listen).mock.calls.find(([name]) => name === eventName);
      expect(registration).toBeDefined();
      registration![1]({ event: eventName, id: 1, payload: null });
      expect(handler).toHaveBeenCalledOnce();
    }
    unbind();
    expect(unlisten).toHaveBeenCalledTimes(vi.mocked(listen).mock.calls.length);
  });

  it("does not register native events outside Tauri", async () => {
    vi.mocked(isTauriAvailable).mockReturnValue(false);
    const unbind = await bindProjectMenuActions({ open: vi.fn(), save: vi.fn(), saveAs: vi.fn() });
    unbind();
    expect(listen).not.toHaveBeenCalled();
  });

  it("dispatches only recognised native simulation commands", async () => {
    vi.mocked(isTauriAvailable).mockReturnValue(true);
    vi.mocked(listen).mockResolvedValue(vi.fn());
    const simulate = vi.fn();
    const unbind = await bindProjectMenuActions({ simulate, open: vi.fn(), save: vi.fn(), saveAs: vi.fn() });
    const handler = vi.mocked(listen).mock.calls.find(([name]) => name === "menu:simulate")![1];
    for (const payload of ["driver", "run", "move", "force", "fields", "advanced"]) handler({ event: "menu:simulate", id: 1, payload });
    expect(simulate).toHaveBeenCalledTimes(6);
    handler({ event: "menu:simulate", id: 1, payload: "fixture" });
    handler({ event: "menu:simulate", id: 1, payload: null });
    expect(simulate).toHaveBeenCalledTimes(6);
    unbind();
  });
});
