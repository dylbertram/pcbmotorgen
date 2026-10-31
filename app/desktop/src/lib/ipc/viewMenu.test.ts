import { beforeEach, expect, it, vi } from "vitest";
import { publishViewMenu, listenViewMenu } from "./viewMenu";
const mocks = vi.hoisted(() => ({ native: false, invoke: vi.fn(), listen: vi.fn() }));
vi.mock("./core", () => ({ isTauriAvailable: () => mocks.native }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: mocks.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: mocks.listen }));
beforeEach(() => { mocks.native = false; mocks.invoke.mockReset(); mocks.listen.mockReset(); });

it("leaves browser previews without native calls", async () => {
  await publishViewMenu({ owner: null, items: [] });
  (await listenViewMenu(() => {}))();
  expect(mocks.invoke).not.toHaveBeenCalled();
  expect(mocks.listen).not.toHaveBeenCalled();
});

it("publishes the authoritative snapshot and forwards the owner-scoped native event", async () => {
  mocks.native = true;
  const cleanup = vi.fn(); mocks.listen.mockResolvedValue(cleanup);
  const state = { owner: "test-viewport", items: [{ id: "view:top", checked: true, enabled: true }] };
  await publishViewMenu(state);
  expect(mocks.invoke).toHaveBeenCalledWith("set_view_menu_state", { state });
  const handle = vi.fn();
  const unlisten = await listenViewMenu(handle);
  expect(mocks.listen.mock.calls[0][0]).toBe("menu:view");
  mocks.listen.mock.calls[0][1]({ payload: { owner: "test-viewport", id: "view:3d" } });
  expect(handle).toHaveBeenCalledWith({ owner: "test-viewport", id: "view:3d" });
  unlisten(); expect(cleanup).toHaveBeenCalledOnce();
});
