import { describe, expect, it, vi } from "vitest";
import { CoilPreviewViewState } from "./components/design/coilPreviewViewState.svelte";
import { applyViewMenuAction, VIEW_MENU_GROUPS, viewMenuItems, type ViewMenuAction, type ViewMenuState } from "./viewMenu";
import { ViewMenuController } from "./viewMenuController";

const capabilities = { active: true, polePitch: true, bandWidths: true, poleRegions: true };
describe("shared View menu", () => {
  it("uses six separated groups without any phase/layer filters", () => {
    expect(VIEW_MENU_GROUPS).toHaveLength(6);
    expect(VIEW_MENU_GROUPS[3].map((item) => item.id)).toEqual(["view:pole-pitch", "view:band-widths", "view:pole-regions"]);
    expect(VIEW_MENU_GROUPS.flat().map((item) => item.property)).not.toContain("layerVisibility");
    expect(VIEW_MENU_GROUPS.flat().map((item) => item.property)).not.toContain("phaseVisibility");
    expect(VIEW_MENU_GROUPS.flat().map((item) => item.property)).not.toContain("poleRegionPhase");
  });
  it("mirrors checks both ways and keeps view/trace choices exclusive", () => {
    const view = new CoilPreviewViewState();
    const checked = () => viewMenuItems(view, capabilities).filter((item) => item.checked).map((item) => item.id);
    expect(checked()).toContain("view:top");
    applyViewMenuAction(view, "view:3d");
    applyViewMenuAction(view, "view:centerlines");
    expect(checked()).toContain("view:3d");
    expect(checked()).not.toContain("view:top");
    expect(checked()).toContain("view:centerlines");
    expect(checked()).not.toContain("view:traces");
    applyViewMenuAction(view, "view:pole-pitch");
    expect(view.showPolePitch).toBe(false);
    view.showVias = false;
    expect(checked()).not.toContain("view:vias");
    const before = JSON.stringify(view.layerVisibility);
    applyViewMenuAction(view, "view:layer-0");
    expect(JSON.stringify(view.layerVisibility)).toBe(before);
  });
  it("disables unavailable overlays and inactive/no-document menus", () => {
    const view = new CoilPreviewViewState();
    expect(viewMenuItems(view, { ...capabilities, polePitch: false }).find((item) => item.id === "view:pole-pitch")?.enabled).toBe(false);
    expect(viewMenuItems(view, { ...capabilities, active: false }).every((item) => !item.enabled)).toBe(true);
    expect(viewMenuItems(null, capabilities).every((item) => !item.enabled && !item.checked)).toBe(true);
  });
});

describe("native View menu ownership", () => {
  it("ignores stale document events and old cleanup without disabling the new document", async () => {
    const handlers: ((action: ViewMenuAction) => void)[] = [];
    const publish = vi.fn(async (_state: ViewMenuState) => {});
    const controller = new ViewMenuController(publish, async handler => { handlers.push(handler); return () => {}; });
    const a = new CoilPreviewViewState(), b = new CoilPreviewViewState();
    const first = controller.connect(() => viewMenuItems(a, capabilities), id => applyViewMenuAction(a, id));
    first.update();
    await vi.waitFor(() => expect(publish).toHaveBeenCalledTimes(1));
    const ownerA = publish.mock.calls[0][0].owner!;
    const second = controller.connect(() => viewMenuItems(b, capabilities), id => applyViewMenuAction(b, id));
    second.update();
    await vi.waitFor(() => expect(publish).toHaveBeenCalledTimes(2));
    const ownerB = publish.mock.calls[1][0].owner!;
    first.dispose();
    handlers[0]({ owner: ownerA, id: "view:3d" });
    expect(a.viewMode).toBe("top");
    expect(b.viewMode).toBe("top");
    handlers[1]({ owner: ownerB, id: "view:3d" });
    expect(b.viewMode).toBe("iso");
    second.dispose();
    await vi.waitFor(() => expect(publish.mock.calls.at(-1)![0].owner).toBeNull());
  });
  it("serializes writes and coalesces pending UI changes to the latest state", async () => {
    let release!: () => void;
    const firstWrite = new Promise<void>(resolve => { release = resolve; });
    const publish = vi.fn().mockImplementationOnce(() => firstWrite).mockResolvedValue(undefined);
    const controller = new ViewMenuController(publish, async () => () => {});
    const view = new CoilPreviewViewState();
    const connection = controller.connect(() => viewMenuItems(view, capabilities), () => {});
    connection.update();
    view.showVias = false; connection.update();
    view.showVias = true; connection.update();
    expect(publish).toHaveBeenCalledTimes(1);
    release();
    await vi.waitFor(() => expect(publish).toHaveBeenCalledTimes(2));
    expect(publish.mock.calls[1][0].items.find((item: { id: string }) => item.id === "view:vias").checked).toBe(true);
    connection.dispose();
  });
  it("disposes a listener that finishes registering after unmount", async () => {
    let ready!: (cleanup: () => void) => void;
    const pending = new Promise<() => void>(resolve => { ready = resolve; });
    const controller = new ViewMenuController(async () => {}, () => pending);
    const connection = controller.connect(() => [], () => {});
    connection.dispose();
    const cleanup = vi.fn(); ready(cleanup);
    await vi.waitFor(() => expect(cleanup).toHaveBeenCalledOnce());
  });
});
