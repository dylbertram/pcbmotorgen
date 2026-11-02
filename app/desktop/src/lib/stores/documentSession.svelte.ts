import { ConfigStore } from "./config.svelte";
import { SensorStore } from "../sensor/sensor.svelte";
import { MotionStore } from "./motion.svelte";
import { ProjectStore } from "./project.svelte";
import type { RecentFilesStore } from "./recentFiles.svelte";
import type { DocumentKind, ForceSweepResult, CoilPathDto, HeightStackResultDto, DriveAnalysis } from "../types";
import { PreviewCamera } from "../preview/previewCamera.svelte";
import { CoilPreviewViewState } from "../preview/coilPreviewViewState.svelte";

let nextDocumentId = 1;

/** Presentation state belongs to an editor view, not the saved file. */
export class DocumentView {
  readonly analysis = $state<{ simulationView: "move" | "force" | "advanced" }>({ simulationView: "move" });
  readonly camera = new PreviewCamera();
  readonly previewView = new CoilPreviewViewState();
  runtime: {
    coils: CoilPathDto | null; sweep: ForceSweepResult | null;
    height: HeightStackResultDto | null;
    drive: DriveAnalysis | null;
  } = { coils: null, sweep: null, height: null, drive: null };
}

/** One saved model per file; editor groups can share it without copying it. */
export class DocumentSession extends DocumentView {
  readonly id = nextDocumentId++;
  readonly config = new ConfigStore();
  readonly sensor = new SensorStore();
  readonly motion = new MotionStore(this.config);
  readonly projects: ProjectStore;
  get title(): string { return this.projects.fileName ?? `Untitled ${this.kind} ${this.id}`; }

  constructor(readonly kind: DocumentKind, recents?: RecentFilesStore) {
    super();
    this.projects = new ProjectStore(this.config, this.motion, recents, this.sensor, kind);
  }

  async initialize(): Promise<void> {
    await Promise.all([this.config.loadRoutingPatterns(), this.config.loadMagnetGrades()]);
    await this.config.loadRoutingParams(this.config.routing_pattern);
    this.projects.markClean();
  }
}
