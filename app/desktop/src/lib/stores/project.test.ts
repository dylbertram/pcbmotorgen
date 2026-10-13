import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConfigStore } from "./config.svelte";
import { MotionStore } from "./motion.svelte";
import { ProjectStore } from "./project.svelte";
import { SensorStore } from "./sensor.svelte";
import { RecentFilesStore } from "./recentFiles.svelte";
import type { ProjectState } from "../types";
import type { CadGeometry } from "../types";
import type { LoadProjectResult } from "../types";
import { confirmDiscardChanges, loadProject, saveProject, pickProjectSavePath, updateProjectVersion, relocateProject } from "../ipc";

// Track load calls without losing the real module's other exports (the
// config store uses them for its routing-pattern/magnet-grade catalog).
vi.mock("../ipc", { spy: true });

/**
 * Unit coverage of the frontend HALF of project persistence (kata 0cgm):
 * snapshot mapping, dirty tracking, and the restore mapping. The Rust
 * artifact round-trip lives in `src-tauri/src/ipc/project.rs`.
 */

function makeStores(recents?: RecentFilesStore) {
  const config = new ConfigStore();
  const motion = new MotionStore(config);
  const sensor = new SensorStore();
  const projects = new ProjectStore(config, motion, recents, sensor);
  return { config, motion, sensor, projects };
}

describe("title-bar project name and location", () => {
  beforeEach(() => vi.clearAllMocks());

  it("moves the artifact without saving the draft or changing the active version", async () => {
    const { recents } = makeRecents();
    await recents.record("/old/design.pmproj");
    const { config, projects } = makeStores(recents);
    projects.currentPath = "/old/design.pmproj";
    projects.activeVersionId = 3;
    projects.versions = [{ id: 3, description: "Original", created_at_unix_ms: 1, last_edited_at_unix_ms: 2 }];
    projects.markClean();
    const baseline = projects.savedSnapshot;
    config.magnet_count = 8;
    vi.mocked(relocateProject).mockResolvedValue({ path: "/new/renamed.pmproj", active_version_id: 3, versions: [], format_version: 2, saved_at_unix_ms: 2 });

    expect(await projects.relocate("renamed", "/new")).toBe(true);
    expect(relocateProject).toHaveBeenCalledWith("/old/design.pmproj", "/new", "renamed", projects.snapshotIpc(), 3);
    expect(projects.currentPath).toBe("/new/renamed.pmproj");
    expect(projects.directory).toBe("/new/");
    expect(projects.activeVersionId).toBe(3);
    expect(projects.versions).toHaveLength(1);
    expect(projects.savedSnapshot).toBe(baseline);
    expect(projects.isDirty).toBe(true);
    expect(config.magnet_count).toBe(8);
    expect(recents.paths).toEqual(["/new/renamed.pmproj"]);
    expect(saveProject).not.toHaveBeenCalled();
  });

  it("creates an untitled project's first saved version", async () => {
    const { projects } = makeStores();
    vi.mocked(relocateProject).mockResolvedValue({ path: "/design.pmproj", active_version_id: 1, versions: [{ id: 1, description: "", created_at_unix_ms: 1, last_edited_at_unix_ms: 1 }], format_version: 2, saved_at_unix_ms: 1 });
    expect(projects.directory).toBeNull();
    expect(await projects.relocate("design", "/")).toBe(true);
    expect(projects.directory).toBe("/");
    expect(projects.label).toBe("design.pmproj");
    expect(projects.activeVersionId).toBe(1);
    expect(projects.versions).toHaveLength(1);
    expect(projects.isDirty).toBe(false);
    expect(projects.savedSnapshot).not.toBeNull();
  });

  it("keeps the original path, draft and baseline after a failure", async () => {
    const { projects, config } = makeStores();
    projects.currentPath = "/old.pmproj";
    projects.markClean();
    const baseline = projects.savedSnapshot;
    config.magnet_count = 8;
    vi.mocked(relocateProject).mockRejectedValue(new Error("Destination already exists"));
    expect(await projects.relocate("new", "/")).toBe(false);
    expect(projects.currentPath).toBe("/old.pmproj");
    expect(projects.savedSnapshot).toBe(baseline);
    expect(projects.isDirty).toBe(true);
    expect(projects.error).toContain("Destination already exists");
    expect(projects.busy).toBe(false);
  });

  it("serializes moves with other file operations", async () => {
    const { projects } = makeStores();
    projects.busy = true;
    expect(await projects.relocate("design", "/")).toBe(false);
    expect(relocateProject).not.toHaveBeenCalled();
  });
});

/** Recents store over a fake port (exposes saved/synced snapshots). */
function makeRecents() {
  const saved: string[][] = [];
  const synced: string[][] = [];
  const port = {
    load: async () => null,
    persist: async (paths: string[]) => {
      saved.push([...paths]);
    },
    exists: async () => true,
    syncMenu: async (paths: string[]) => {
      synced.push([...paths]);
    },
  };
  const recents = new RecentFilesStore(port as never);
  return { recents, saved, synced };
}

/** Apply a realistic set of edits across all persisted groups. */
function editDesign(config: ConfigStore, motion: MotionStore): void {
  config.desired_travel_mm = 60;
  config.active_area_width_mm = 25;
  config.strands_per_phase = 1;
  config.magnet_count = 16;
  config.magnet_width_mm = 5.0;
  config.magnet_cross_width_mm = 12;
  config.magnet_height_mm = 3.5;
  config.magnet_grade = "N52";
  config.magnet_remanence_t = 1.43;
  config.air_gap_mm = 0.75;
  config.electrical_pitch_mm = 14;
  config.routing_pattern = "quad-stack";
  config.setRoutingParam("num_strands", 3);
  config.phases = 4;
  config.num_layers = 6;
  config.max_current_a = 2.5;
  config.supply_voltage_v = 12;
  config.target_force_n = 1.2;
  config.peak_force_n = 2.0;
  config.friction_n = 0.1;
  config.carriage_mass_kg = 0.02;
  config.max_accel_m_s2 = 3;
  config.capacitor_bank_uf = 2200;
  config.commutation = "phase_a_only";
  config.n_positions = 100;
  config.meshing = 30;
  config.min_trace_mm = 0.2;
  config.min_space_mm = 0.2;
  config.min_via_drill_mm = 0.3;
  config.min_via_annular_ring_mm = 0.15;
  config.pcb_thickness_mm = 2.0;
  config.max_layers = 8;
  config.drive_frequency_hz = 1000;
  config.max_temperature_rise_c = 30;
  motion.positionMm = 42.5;
}

describe("ProjectStore snapshot mapping", () => {
  it("persists sensor CAD separately and clears it when loading older projects", () => {
    const { config, sensor, projects } = makeStores();
    const legacy = projects.snapshotIpc();
    delete legacy.sensor_cad_geometry;
    projects.markClean();
    const geometry: CadGeometry = {
      routing: { format_version: 1, segments: [{ start: { x: 0, y: 0 }, end: { x: 20, y: 2 }, layer: 0, net: "CL1", is_active: true }], curves: [], vias: [] },
      layer_z_mm: [-0.8, 0.8], trace_width_mm: 0.2,
    };
    sensor.cadGeometry = geometry;
    expect(projects.isDirty).toBe(true);
    expect(projects.cadGeometry).toBeNull();
    expect(config.num_layers).toBe(4);
    const state = projects.snapshotIpc();
    const restored = makeStores();
    restored.projects.applyToState(state);
    expect(restored.sensor.cadGeometry).toEqual(geometry);
    expect(restored.sensor.geometry?.nets[0].name).toBe("CL1");
    expect(restored.sensor.geometry?.board_bounds_mm).toEqual([0, 0, 20, 2]);
    restored.sensor.set("lambda_mm", 240);
    expect(restored.sensor.geometry?.nets[0].segments).toEqual(geometry.routing.segments);
    restored.projects.applyToState(legacy);
    expect(restored.sensor.cadGeometry).toBeNull();
  });

  it("uses sensor defaults when no sensor store is supplied", () => {
    const config = new ConfigStore();
    const motion = new MotionStore(config);
    const projects = new ProjectStore(config, motion);
    expect(projects.snapshotIpc().sensor_config?.lambda_mm).toBe(120);
  });

  it("tracks sensor-only edits and restores defaults from older projects", () => {
    const { sensor, projects } = makeStores();
    const legacy = projects.snapshotIpc();
    delete legacy.sensor_config;
    projects.markClean();
    sensor.set("tx_trace_width_mm", 0.3);
    expect(projects.isDirty).toBe(true);
    projects.applyToState(legacy);
    expect(sensor.config.tx_trace_width_mm).toBe(0.15);
    expect(sensor.config.lambda_mm).toBe(120);
  });
  it("captures every persisted input group in UI units", () => {
    const { config, motion, projects } = makeStores();
    editDesign(config, motion);
    const state = projects.snapshotIpc();

    expect(state.mover_position_mm).toBe(42.5);
    const c = state.config;
    expect(c.desired_travel_mm).toBe(60);
    expect(c.magnet_grade).toBe("N52");
    expect(c.routing_pattern).toBe("quad-stack");
    expect(c.routing_params.num_strands).toBe(3);
    expect(c.commutation).toBe("phase_a_only");
    expect(c.num_layers).toBe(6);
    expect(c.min_trace_mm).toBe(0.2);
    expect(c.capacitor_bank_uf).toBe(2200);
    expect(state.sensor_config?.lambda_mm).toBe(120);
  });

  it("persists sensor edits independently from motor travel", () => {
    const { config, sensor, projects } = makeStores();
    projects.markClean();
    config.desired_travel_mm = 120;
    expect(sensor.config.lambda_mm).toBe(120);
    expect(projects.isDirty).toBe(true);
    sensor.set("lambda_mm", 240);
    sensor.set("tx_trace_width_mm", 0.2);
    const state = projects.snapshotIpc();
    expect(state.sensor_config?.lambda_mm).toBe(240);
    expect(state.sensor_config?.tx_trace_width_mm).toBe(0.2);

    const restored = makeStores();
    restored.projects.applyToState(state);
    expect(restored.sensor.config.lambda_mm).toBe(240);
    expect(restored.sensor.config.tx_trace_width_mm).toBe(0.2);
  });

  it("serializes routing params with sorted keys for a stable snapshot", () => {
    const a = makeStores();
    const b = makeStores();
    // Same two params inserted in opposite orders across two stores.
    a.config.setRoutingParam("aaa", 1);
    a.config.setRoutingParam("zzz", 2);
    b.config.setRoutingParam("zzz", 2);
    b.config.setRoutingParam("aaa", 1);
    expect(a.projects.snapshotJson).toBe(b.projects.snapshotJson);
  });
});

describe("ProjectStore dirty tracking", () => {
  it("is clean until the first baseline (untitled design)", () => {
    const { projects } = makeStores();
    expect(projects.savedSnapshot).toBeNull();
    expect(projects.isDirty).toBe(false);
  });

  it("goes dirty on an input change after a baseline, clean after markClean", () => {
    const { config, projects } = makeStores();
    projects.markClean();
    expect(projects.isDirty).toBe(false);

    config.desired_travel_mm = 80;
    expect(projects.isDirty).toBe(true);

    projects.markClean();
    expect(projects.isDirty).toBe(false);
  });

  it("detects mover-position edits", () => {
    const { motion, projects } = makeStores();
    projects.markClean();
    motion.positionMm = 10;
    expect(projects.isDirty).toBe(true);
  });

  it("tracks imported geometry and preserves it across a project snapshot", () => {
    const { projects } = makeStores();
    projects.markClean();
    const geometry: CadGeometry = {
      routing: { format_version: 2, segments: [], curves: [], vias: [] },
      layer_z_mm: [-0.8, 0.8],
      trace_width_mm: 0.2,
      source_file_name: "motor-coils.dxf",
    };
    projects.setCadGeometry(geometry);
    expect(projects.isDirty).toBe(true);
    const target = makeStores().projects;
    target.applyToState(projects.snapshotIpc());
    expect(target.cadGeometry).toEqual(geometry);
    expect(target.snapshotIpc().cad_geometry).toEqual(geometry);
    expect(target.cadGeometry?.source_file_name).toBe("motor-coils.dxf");
  });

  it("reports the file name and untitled label", () => {
    const { projects } = makeStores();
    expect(projects.label).toBe("untitled design");
    projects.currentPath = "/home/user/designs/my-motor.pmproj";
    expect(projects.fileName).toBe("my-motor.pmproj");
    expect(projects.label).toBe("my-motor.pmproj");
  });
});

describe("ProjectStore openPath (kata eap8)", () => {
  beforeEach(() => {
    vi.mocked(loadProject).mockReset();
  });

  it("opens a given path through the real flow and records the recents entry", async () => {
    const { recents, saved, synced } = makeRecents();
    const { config, motion, projects } = makeStores(recents);
    const state: ProjectState = {
      config: {
        ...projects.snapshotIpc().config,
        desired_travel_mm: 60,
      },
      mover_position_mm: 7,
    };
    const result: LoadProjectResult = {
      project: state,
      source_format_version: 1,
      format_version: 1,
      validation: { errors: [], warnings: [] },
      active_version_id: 1,
      versions: [{ id: 1, description: "Original", created_at_unix_ms: 100, last_edited_at_unix_ms: 100 }],
    };
    vi.mocked(loadProject).mockResolvedValue(result);

    projects.markClean(); // clean: no discard-confirm path
    projects.notice = "Previous notification";
    const ok = await projects.openPath("/home/user/motor-1.pmproj");
    expect(ok).toBe(true);
    expect(loadProject).toHaveBeenCalledWith("/home/user/motor-1.pmproj", null);
    expect(projects.currentPath).toBe("/home/user/motor-1.pmproj");
    expect(projects.error).toBeNull();
    expect(projects.notice).toBeNull();
    expect(motion.positionMm).toBe(7);
    expect(config.desired_travel_mm).toBe(60);

    // The recents record happens in the background — flush it.
    await new Promise((r) => setTimeout(r, 0));
    expect(saved).toEqual([["/home/user/motor-1.pmproj"]]);
    expect(synced).toEqual([[], ["/home/user/motor-1.pmproj"]]);
  });

  it("keeps restored-project warnings without an opened-file notification", async () => {
    const { projects } = makeStores();
    vi.mocked(loadProject).mockResolvedValue({
      project: projects.snapshotIpc(),
      source_format_version: 2,
      format_version: 2,
      active_version_id: 1,
      versions: [],
      validation: { errors: [], warnings: ["Check the imported geometry"] },
    });
    expect(await projects.openPath("/warned.pmproj")).toBe(true);
    expect(projects.notice).toBeNull();
    expect(projects.loadIssues?.warnings).toEqual(["Check the imported geometry"]);
  });

  it("on backend failure: error UX, no recents record, state untouched", async () => {
    const { recents, saved } = makeRecents();
    const { config, projects, motion } = makeStores(recents);
    vi.mocked(loadProject).mockRejectedValue(
      'could not open "/nope.pmproj": file not found',
    );

    // A real design was in progress when the open was attempted.
    config.desired_travel_mm = 60;
    motion.positionMm = 42.5;
    projects.markClean();
    const ok = await projects.openPath("/nope.pmproj");
    expect(ok).toBe(false);
    expect(projects.currentPath).toBeNull();
    expect(projects.error).toBe(
      'Open failed — could not open "/nope.pmproj": file not found',
    );

    await new Promise((r) => setTimeout(r, 0));
    expect(saved).toEqual([]);

    // The rejected open did not restore over the in-progress state.
    expect(motion.positionMm).toBe(42.5);
    expect(config.desired_travel_mm).toBe(60);
  });
});

describe("ProjectStore newProject", () => {
  beforeEach(() => {
    vi.mocked(confirmDiscardChanges).mockReset();
  });

  it("resets motor, sensor, mover, file path, CAD, and messages", async () => {
    const { config, motion, sensor, projects } = makeStores();
    const defaults = projects.snapshotIpc();
    editDesign(config, motion);
    sensor.set("lambda_mm", 240);
    projects.currentPath = "/saved.pmproj";
    projects.cadGeometry = { trace_width_mm: 0.2 } as CadGeometry;
    projects.error = "Previous failure";
    projects.markClean();

    expect(await projects.newProject()).toBe(true);
    expect(projects.snapshotIpc().config.desired_travel_mm).toBe(defaults.config.desired_travel_mm);
    expect(projects.snapshotIpc().sensor_config).toEqual(defaults.sensor_config);
    expect(motion.positionMm).toBe(defaults.mover_position_mm);
    expect(projects.currentPath).toBeNull();
    expect(projects.cadGeometry).toBeNull();
    expect(projects.error).toBeNull();
    expect(projects.isDirty).toBe(false);
    config.desired_travel_mm += 1;
    expect(projects.isDirty).toBe(true);
  });

  it("keeps the entire working state when discard is cancelled", async () => {
    const { config, projects } = makeStores();
    projects.currentPath = "/saved.pmproj";
    projects.markClean();
    config.desired_travel_mm = 42;
    const before = projects.snapshotJson;
    vi.mocked(confirmDiscardChanges).mockResolvedValue(false);

    expect(await projects.newProject()).toBe(false);
    expect(confirmDiscardChanges).toHaveBeenCalledOnce();
    expect(projects.snapshotJson).toBe(before);
    expect(projects.currentPath).toBe("/saved.pmproj");
    expect(projects.busy).toBe(false);
  });

  it("requires confirmation for unsaved changes and ignores overlapping New", async () => {
    const { config, projects } = makeStores();
    projects.markClean();
    config.desired_travel_mm = 42;
    let confirm!: (value: boolean) => void;
    vi.mocked(confirmDiscardChanges).mockReturnValue(new Promise((resolve) => { confirm = resolve; }));
    const pending = projects.newProject();
    expect(projects.busy).toBe(true);
    expect(await projects.newProject()).toBe(false);
    confirm(true);
    expect(await pending).toBe(true);
    expect(projects.isDirty).toBe(false);
    expect(projects.busy).toBe(false);
  });
});

describe("ProjectStore versions", () => {
  const versions = [
    { id: 1, description: "Original", created_at_unix_ms: 100, last_edited_at_unix_ms: 100 },
    { id: 2, description: "Short track", created_at_unix_ms: 200, last_edited_at_unix_ms: 200 },
  ];

  beforeEach(() => {
    vi.mocked(loadProject).mockReset();
    vi.mocked(saveProject).mockReset();
    vi.mocked(updateProjectVersion).mockReset();
    vi.mocked(pickProjectSavePath).mockReset();
    vi.mocked(confirmDiscardChanges).mockReset();
  });

  function savedStores() {
    const stores = makeStores();
    stores.projects.currentPath = "/project.pmproj";
    stores.projects.versions = versions;
    stores.projects.activeVersionId = 2;
    stores.projects.markClean();
    return stores;
  }

  function loadResult(project: ProjectState, id = 1, remaining = versions): LoadProjectResult {
    return { project, active_version_id: id, versions: remaining, format_version: 2, source_format_version: 2, validation: { errors: [], warnings: [] } };
  }

  it("Save updates the selected version and Save new version forks it", async () => {
    const { projects } = savedStores();
    vi.mocked(saveProject).mockResolvedValue({ path: "/project.pmproj", format_version: 2, saved_at_unix_ms: 300, active_version_id: 2, versions });
    expect(await projects.save()).toBe(true);
    expect(saveProject).toHaveBeenLastCalledWith("/project.pmproj", projects.snapshotIpc(), { sourcePath: "/project.pmproj", activeVersionId: 2, newVersion: false, description: undefined });
    const forked = [...versions, { ...versions[1], id: 3, description: "Experiment" }];
    vi.mocked(saveProject).mockResolvedValue({ path: "/project.pmproj", format_version: 2, saved_at_unix_ms: 400, active_version_id: 3, versions: forked });
    expect(await projects.save(false, true, "Experiment")).toBe(true);
    expect(saveProject).toHaveBeenLastCalledWith("/project.pmproj", projects.snapshotIpc(), { sourcePath: "/project.pmproj", activeVersionId: 2, newVersion: true, description: "Experiment" });
    expect(projects.activeVersionId).toBe(3);
    expect(projects.versions).toEqual(forked);
  });

  it("Save As carries the source file so the backend preserves every version", async () => {
    const { projects } = savedStores();
    vi.mocked(pickProjectSavePath).mockResolvedValue("/copy.pmproj");
    vi.mocked(saveProject).mockResolvedValue({ path: "/copy.pmproj", format_version: 2, saved_at_unix_ms: 300, active_version_id: 2, versions });
    expect(await projects.save(true)).toBe(true);
    expect(saveProject).toHaveBeenCalledWith("/copy.pmproj", projects.snapshotIpc(), expect.objectContaining({ sourcePath: "/project.pmproj" }));
    expect(projects.currentPath).toBe("/copy.pmproj");
    expect(projects.versions).toEqual(versions);
  });

  it("opening a version protects unsaved changes and does not touch disk on cancel", async () => {
    const { config, projects } = savedStores();
    const original = projects.snapshotIpc();
    config.desired_travel_mm = 99;
    vi.mocked(confirmDiscardChanges).mockResolvedValue(false);
    expect(await projects.openVersion(1)).toBe(false);
    expect(loadProject).not.toHaveBeenCalled();
    expect(config.desired_travel_mm).toBe(99);
    vi.mocked(confirmDiscardChanges).mockResolvedValue(true);
    vi.mocked(loadProject).mockResolvedValue(loadResult(original));
    expect(await projects.openVersion(1)).toBe(true);
    expect(loadProject).toHaveBeenCalledWith("/project.pmproj", 1);
    expect(projects.activeVersionId).toBe(1);
    expect(projects.isDirty).toBe(false);
  });

  it("description edits and deleting an inactive version preserve the unsaved draft", async () => {
    const { config, projects } = savedStores();
    const saved = projects.snapshotIpc();
    config.desired_travel_mm = 99;
    const changed = [{ ...versions[0], description: "Edited", last_edited_at_unix_ms: 300 }, versions[1]];
    vi.mocked(updateProjectVersion).mockResolvedValue(loadResult(saved, 2, changed));
    expect(await projects.describeVersion(1, "Edited")).toBe(true);
    expect(projects.versions[0].description).toBe("Edited");
    expect(config.desired_travel_mm).toBe(99);
    expect(projects.isDirty).toBe(true);
    vi.mocked(updateProjectVersion).mockResolvedValue(loadResult(saved, 2, [versions[1]]));
    expect(await projects.deleteVersion(1)).toBe(true);
    expect(config.desired_travel_mm).toBe(99);
    expect(projects.activeVersionId).toBe(2);
    expect(projects.isDirty).toBe(true);
    expect(await projects.deleteVersion(2)).toBe(false);
  });

  it("deleting the active version restores the remaining version", async () => {
    const { config, projects } = savedStores();
    const original = projects.snapshotIpc();
    config.desired_travel_mm = 99;
    vi.mocked(updateProjectVersion).mockResolvedValue(loadResult(original, 1, [versions[0]]));
    expect(await projects.deleteVersion(2)).toBe(true);
    expect(projects.activeVersionId).toBe(1);
    expect(config.desired_travel_mm).toBe(original.config.desired_travel_mm);
    expect(projects.isDirty).toBe(false);
  });

  it("failed version operations keep the current version and draft unchanged", async () => {
    const { config, projects } = savedStores();
    config.desired_travel_mm = 99;
    vi.mocked(updateProjectVersion).mockRejectedValue(new Error("Disk unavailable"));
    expect(await projects.deleteVersion(2)).toBe(false);
    expect(await projects.describeVersion(1, "Edited")).toBe(false);
    vi.mocked(saveProject).mockRejectedValue(new Error("Disk full"));
    expect(await projects.save(false, true)).toBe(false);
    expect(projects.activeVersionId).toBe(2);
    expect(projects.versions).toEqual(versions);
    expect(config.desired_travel_mm).toBe(99);
    expect(projects.isDirty).toBe(true);
  });

  it("edits made during a save remain dirty and overlapping saves are ignored", async () => {
    const { config, projects } = savedStores();
    let finish!: (value: Awaited<ReturnType<typeof saveProject>>) => void;
    vi.mocked(saveProject).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const pending = projects.save();
    expect(await projects.save()).toBe(false);
    config.desired_travel_mm = 99;
    finish({ path: "/project.pmproj", format_version: 2, saved_at_unix_ms: 300, active_version_id: 2, versions });
    expect(await pending).toBe(true);
    expect(projects.isDirty).toBe(true);
  });
});

describe("ProjectStore restore mapping", () => {
  it("round-trips a snapshot into a fresh store set", () => {
    const source = makeStores();
    editDesign(source.config, source.motion);
    const state: ProjectState = source.projects.snapshotIpc();

    const target = makeStores();
    target.projects.applyToState(state);

    // The canonical snapshot of the restored stores equals the snapshot
    // of the source — full state restore, no drift.
    expect(target.projects.snapshotJson).toBe(source.projects.snapshotJson);
    expect(target.motion.positionMm).toBe(42.5);
  });

  it("bumps routing_params_version so scheduling effects re-run", () => {
    const { config, projects } = makeStores();
    const before = config.routing_params_version;
    projects.applyToState({
      config: { ...projects.snapshotIpc().config },
      mover_position_mm: 10,
    });
    expect(config.routing_params_version).toBeGreaterThan(before);
  });

  it("copies routing params (later store mutations do not leak back)", () => {
    const source = makeStores();
    source.config.setRoutingParam("num_strands", 3);
    const state = source.projects.snapshotIpc();

    const target = makeStores();
    target.projects.applyToState(state);
    target.config.setRoutingParam("num_strands", 9);

    expect(source.config.routing_params.num_strands).toBe(3);
    expect(target.config.routing_params.num_strands).toBe(9);
  });
});
