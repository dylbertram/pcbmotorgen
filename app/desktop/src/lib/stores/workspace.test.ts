import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceStore, type UnsavedChoice } from "./workspace.svelte";
import { RecentFilesStore } from "./recentFiles.svelte";
import * as ipc from "../ipc";
import { ConfigStore } from "./config.svelte";
import { MotionStore } from "./motion.svelte";
import { ProjectStore } from "./project.svelte";

vi.mock("../ipc", { spy: true });

function fixture() {
  const config = new ConfigStore();
  return new ProjectStore(config, new MotionStore(config)).snapshotIpc();
}

const versions = [{ id: 1, description: "Original", created_at_unix_ms: 100, last_edited_at_unix_ms: 100 }];

function makeWorkspace() {
  const recents = new RecentFilesStore({ load: async () => null, persist: async () => {}, syncMenu: async () => {}, exists: async () => true });
  const choose = vi.fn<(label: string) => Promise<UnsavedChoice>>().mockResolvedValue("discard");
  return { workspace: new WorkspaceStore(recents, choose), choose, recents };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(ipc.resolveDocumentPath).mockImplementation(async p => p);
  vi.mocked(ipc.loadProject).mockImplementation(async () => ({ project: fixture(), active_version_id: 1, versions, format_version: 1, source_format_version: 1, validation: { errors: [], warnings: [] } }));
  vi.mocked(ipc.saveProject).mockImplementation(async (path) => ({ path, active_version_id: 1, versions, format_version: 1, saved_at_unix_ms: 100 }));
  vi.mocked(ipc.saveWorkspace).mockResolvedValue();
  vi.mocked(ipc.pickWorkspaceSavePath).mockResolvedValue("/project.pmproj");
  vi.mocked(ipc.pickProjectSavePath).mockImplementation(async (_, kind) => `/untitled.${kind === "sensor" ? "pmsensor" : "pmmotor"}`);
});

describe("workspace documents", () => {
  it("creates independent files of both types and retains edits while switching", async () => {
    const { workspace } = makeWorkspace();
    await workspace.create("motor");
    const first = workspace.active!;
    first.config.magnet_count = 8;
    first.motion.positionMm = 50;
    first.camera.zoom = 3;
    await workspace.create("motor");
    const second = workspace.active!;
    expect(second.config.magnet_count).toBe(12);
    second.config.magnet_count = 6;
    await workspace.create("sensor");
    workspace.active!.sensor.set("lambda_mm", 240);
    workspace.activate(first.id);
    expect(first.config.magnet_count).toBe(8);
    expect(first.camera.zoom).toBe(3);
    expect(first.projects.isDirty).toBe(true);
    expect(second.config.magnet_count).toBe(6);
    expect(workspace.documents).toHaveLength(3);
  });

  it("tracks only persisted inputs for each document type", async () => {
    const { workspace } = makeWorkspace();
    await workspace.create("sensor");
    const sensor = workspace.active!;
    sensor.config.magnet_count = 4;
    expect(sensor.projects.isDirty).toBe(false);
    sensor.sensor.set("lambda_mm", 240);
    expect(sensor.projects.isDirty).toBe(true);
    await workspace.create("motor");
    const motor = workspace.active!;
    motor.sensor.set("lambda_mm", 360);
    expect(motor.projects.isDirty).toBe(false);
    expect(motor.projects.defaultFileName).toBe("untitled.pmmotor");
    expect(sensor.projects.defaultFileName).toBe("untitled.pmsensor");
  });

  it("opening a coil adds a tab without asking to discard another draft", async () => {
    const { workspace, choose } = makeWorkspace();
    await workspace.create("motor");
    const original = workspace.active!;
    original.config.magnet_count = 8;
    expect(await workspace.openPath("/sensor.pmsensor")).toBe(true);
    expect(workspace.active!.kind).toBe("sensor");
    expect(workspace.documents).toContain(original);
    expect(original.config.magnet_count).toBe(8);
    expect(choose).not.toHaveBeenCalled();
  });

  it("focuses an already-open canonical path rather than creating a duplicate", async () => {
    const { workspace } = makeWorkspace();
    vi.mocked(ipc.resolveDocumentPath).mockResolvedValue("/motor.pmmotor");
    await workspace.openPath("/motor.pmmotor");
    const first = workspace.active!;
    await workspace.create("sensor");
    await workspace.openPath("/alias.pmmotor");
    expect(workspace.active).toBe(first);
    expect(workspace.documents).toHaveLength(2);
  });

  it("cancel closing preserves an untitled document, then discard closes it", async () => {
    const { workspace, choose } = makeWorkspace();
    await workspace.create("motor");
    const document = workspace.active!;
    choose.mockResolvedValueOnce("cancel");
    expect(await workspace.close(document.id)).toBe(false);
    expect(workspace.active).toBe(document);
    expect(await workspace.close(document.id)).toBe(true);
    expect(workspace.active).toBeNull();
    expect(ipc.saveProject).not.toHaveBeenCalled();
  });

  it("a canceled or failed save does not close a document", async () => {
    const { workspace, choose } = makeWorkspace();
    await workspace.create("sensor");
    const document = workspace.active!;
    choose.mockResolvedValue("save");
    vi.mocked(ipc.pickProjectSavePath).mockResolvedValueOnce(null);
    expect(await workspace.close(document.id)).toBe(false);
    vi.mocked(ipc.saveProject).mockRejectedValueOnce(new Error("Disk full"));
    expect(await workspace.close(document.id)).toBe(false);
    expect(workspace.active).toBe(document);
    expect(document.projects.error).toContain("Disk full");
  });

  it("saving on close uses the document's type and removes only that tab", async () => {
    const { workspace, choose } = makeWorkspace();
    await workspace.create("motor");
    const motor = workspace.active!;
    await workspace.create("sensor");
    choose.mockResolvedValue("save");
    expect(await workspace.close(workspace.activeId!)).toBe(true);
    expect(workspace.active).toBe(motor);
    expect(ipc.saveProject).toHaveBeenCalledWith("/untitled.pmsensor", expect.anything(), expect.objectContaining({ kind: "sensor" }));
  });

  it("Save As cannot overwrite a different open tab", async () => {
    const { workspace } = makeWorkspace();
    await workspace.openPath("/existing.pmmotor");
    await workspace.create("motor");
    vi.mocked(ipc.pickProjectSavePath).mockResolvedValueOnce("/existing.pmmotor");
    expect(await workspace.active!.projects.save(true)).toBe(false);
    expect(workspace.active!.projects.error).toContain("already open");
    expect(ipc.saveProject).not.toHaveBeenCalled();
  });

  it("Save All saves independent documents before publishing the manifest", async () => {
    const { workspace } = makeWorkspace();
    await workspace.create("motor");
    await workspace.create("sensor");
    expect(await workspace.saveAll()).toBe(true);
    expect(ipc.saveProject).toHaveBeenCalledTimes(2);
    expect(ipc.saveWorkspace).toHaveBeenCalledWith("/project.pmproj", ["/untitled.pmmotor", "/untitled.pmsensor"], "/untitled.pmsensor");
    expect(workspace.isDirty).toBe(false);
    expect(workspace.documents.every(d => !d.projects.isDirty)).toBe(true);
  });

  it("cancellation never publishes a manifest with untitled references", async () => {
    const { workspace } = makeWorkspace();
    await workspace.create("motor");
    vi.mocked(ipc.pickProjectSavePath).mockResolvedValueOnce(null);
    expect(await workspace.save()).toBe(false);
    expect(ipc.saveWorkspace).not.toHaveBeenCalled();
    expect(workspace.isDirty).toBe(true);
  });

  it("reopens all workspace files and restores the active file", async () => {
    const { workspace } = makeWorkspace();
    vi.mocked(ipc.loadWorkspace).mockResolvedValue({ path: "/project.pmproj", files: ["/motor.pmmotor", "/sensor.pmsensor"], active_file: "/sensor.pmsensor" });
    expect(await workspace.openPath("/project.pmproj")).toBe(true);
    expect(workspace.documents.map(d => d.kind)).toEqual(["motor", "sensor"]);
    expect(workspace.active!.kind).toBe("sensor");
    expect(workspace.path).toBe("/project.pmproj");
    expect(workspace.isDirty).toBe(false);
  });

  it("missing references leave the entire current workspace untouched", async () => {
    const { workspace } = makeWorkspace();
    await workspace.create("motor");
    const original = workspace.active!;
    original.config.magnet_count = 8;
    vi.mocked(ipc.loadWorkspace).mockResolvedValue({ path: "/project.pmproj", files: ["/missing.pmsensor"], active_file: null });
    vi.mocked(ipc.loadProject).mockRejectedValueOnce(new Error("File not found"));
    expect(await workspace.openPath("/project.pmproj")).toBe(false);
    expect(workspace.active).toBe(original);
    expect(original.config.magnet_count).toBe(8);
    expect(workspace.error).toContain("File not found");
  });

  it("New Project can be canceled without replacing any drafts", async () => {
    const { workspace, choose } = makeWorkspace();
    await workspace.create("motor");
    choose.mockResolvedValueOnce("cancel");
    expect(await workspace.newProject()).toBe(false);
    expect(workspace.documents).toHaveLength(1);
    expect(await workspace.newProject()).toBe(true);
    expect(workspace.documents).toHaveLength(0);
    expect(workspace.path).toBeNull();
  });

  it("edits made during a close-save keep the document open and dirty", async () => {
    const { workspace, choose } = makeWorkspace();
    await workspace.openPath("/motor.pmmotor");
    const document = workspace.active!;
    document.config.magnet_count = 8;
    choose.mockResolvedValue("save");
    let finish!: (result: Awaited<ReturnType<typeof ipc.saveProject>>) => void;
    vi.mocked(ipc.saveProject).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const closing = workspace.close(document.id);
    await vi.waitFor(() => expect(finish).toBeTypeOf("function"));
    document.config.magnet_count = 6;
    finish({ path: "/motor.pmmotor", active_version_id: 1, versions, format_version: 1, saved_at_unix_ms: 200 });
    expect(await closing).toBe(false);
    expect(workspace.active).toBe(document);
    expect(document.projects.isDirty).toBe(true);
    expect(workspace.notice).toContain("More edits");
  });

  it("Quit approval saves all drafts and the workspace, while cancel changes nothing", async () => {
    const { workspace, choose } = makeWorkspace();
    await workspace.create("motor");
    await workspace.create("sensor");
    choose.mockResolvedValueOnce("cancel");
    expect(await workspace.canClose()).toBe(false);
    expect(workspace.documents).toHaveLength(2);
    choose.mockResolvedValueOnce("save");
    expect(await workspace.canClose()).toBe(true);
    expect(ipc.saveProject).toHaveBeenCalledTimes(2);
    expect(ipc.saveWorkspace).toHaveBeenCalledTimes(1);
  });

  it("workspace reopening displays edits saved during the replacement confirmation", async () => {
    const { workspace, choose } = makeWorkspace();
    let disk = fixture();
    vi.mocked(ipc.loadProject).mockImplementation(async () => ({ project: structuredClone(disk), active_version_id: 1, versions, format_version: 1, source_format_version: 1, validation: { errors: [], warnings: [] } }));
    vi.mocked(ipc.saveProject).mockImplementation(async (path, state) => {
      disk = JSON.parse(JSON.stringify(state));
      return { path, active_version_id: 1, versions, format_version: 1, saved_at_unix_ms: 200 };
    });
    await workspace.openPath("/motor.pmmotor");
    workspace.active!.config.magnet_count = 8;
    choose.mockResolvedValue("save");
    vi.mocked(ipc.loadWorkspace).mockResolvedValue({ path: "/project.pmproj", files: ["/motor.pmmotor"], active_file: "/motor.pmmotor" });
    expect(await workspace.openPath("/project.pmproj")).toBe(true);
    expect(workspace.active!.config.magnet_count).toBe(8);
    expect(workspace.active!.projects.isDirty).toBe(false);
  });

  it("reference changes during a workspace write do not become falsely clean", async () => {
    const { workspace } = makeWorkspace();
    await workspace.openPath("/motor.pmmotor");
    let finish!: () => void;
    vi.mocked(ipc.saveWorkspace).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const saving = workspace.save();
    await vi.waitFor(() => expect(finish).toBeTypeOf("function"));
    workspace.active!.projects.currentPath = "/renamed.pmmotor";
    finish();
    expect(await saving).toBe(true);
    expect(workspace.isDirty).toBe(true);
  });
});
