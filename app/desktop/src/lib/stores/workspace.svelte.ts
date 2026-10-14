import { ConfigStore } from "./config.svelte";
import { SensorStore } from "./sensor.svelte";
import { MotionStore } from "./motion.svelte";
import { ProjectStore } from "./project.svelte";
import type { RecentFilesStore } from "./recentFiles.svelte";
import type { DocumentKind, WorkspaceLoad, ForceSweepResult, CoilPathDto, FrictionBudgetDto, PowerBudgetDto, HeightStackResultDto, StackupResultDto } from "../types";
import type { TabId } from "../ui";
import { PreviewCamera } from "../utils/coilPreviewGestures.svelte";
import { CoilPreviewViewState } from "../components/design/coilPreviewViewState.svelte";
import { fileExists, loadWorkspace, pickProjectOpenPath, pickWorkspaceSavePath, resolveDocumentPath, saveWorkspace } from "../ipc";

export type UnsavedChoice = "save" | "discard" | "cancel";
export type ResolveUnsaved = (label: string) => Promise<UnsavedChoice>;

let nextDocumentId = 1;

/** One complete working session per file. No editable state is shared by tabs. */
export class DocumentSession {
  readonly id = nextDocumentId++;
  readonly config = new ConfigStore();
  readonly sensor = new SensorStore();
  readonly motion = new MotionStore(this.config);
  readonly projects: ProjectStore;
  readonly camera = new PreviewCamera();
  readonly previewView = new CoilPreviewViewState();
  runtime: {
    activeTab: TabId; coils: CoilPathDto | null; sweep: ForceSweepResult | null;
    friction: FrictionBudgetDto | null; power: PowerBudgetDto | null;
    height: HeightStackResultDto | null; stackup: StackupResultDto | null;
  } = { activeTab: "design", coils: null, sweep: null, friction: null, power: null, height: null, stackup: null };

  constructor(readonly kind: DocumentKind, recents?: RecentFilesStore) {
    this.projects = new ProjectStore(this.config, this.motion, recents, this.sensor, kind);
  }

  async initialize(): Promise<void> {
    await Promise.all([this.config.loadRoutingPatterns(), this.config.loadMagnetGrades()]);
    await this.config.loadRoutingParams(this.config.routing_pattern);
    this.projects.markClean();
  }
}

function message(error: unknown): string { return error instanceof Error ? error.message : String(error); }
function baseName(path: string): string { return path.split(/[\\/]/).pop() ?? path; }

export class WorkspaceStore {
  documents = $state.raw<DocumentSession[]>([]);
  activeId = $state<number | null>(null);
  path = $state<string | null>(null);
  busy = $state(false);
  error = $state<string | null>(null);
  notice = $state<string | null>(null);
  private baseline = $state("[]");
  active = $derived(this.documents.find(d => d.id === this.activeId) ?? null);
  label = $derived(this.path ? baseName(this.path) : "Untitled project");
  fingerprint = $derived(JSON.stringify(this.documents.map(d => d.projects.currentPath ?? `untitled:${d.id}`)));
  isDirty = $derived(this.fingerprint !== this.baseline);
  pending = $derived(this.busy || this.documents.some(d => d.projects.busy));
  directories = $derived.by(() => {
    const dirs: string[] = [];
    const add = (dir: string | null) => {
      if (dir && !dirs.includes(dir)) dirs.push(dir);
    };
    if (this.path) {
      const idx = Math.max(this.path.lastIndexOf("/"), this.path.lastIndexOf("\\"));
      if (idx >= 0) add(this.path.slice(0, idx + 1));
    }
    if (this.active) add(this.active.projects.directory);
    for (const d of this.documents) add(d.projects.directory);
    return dirs;
  });

  constructor(private readonly recents: RecentFilesStore, private readonly resolveUnsaved: ResolveUnsaved) {}

  activate(id: number): void {
    if (!this.pending && this.documents.some(d => d.id === id)) this.activeId = id;
  }

  private attach(document: DocumentSession): void {
    document.projects.checkSavePath = async (path) => {
      if (await fileExists(path)) path = await resolveDocumentPath(path);
      if (this.documents.some(d => d !== document && d.projects.currentPath === path)) {
        throw new Error("This file is already open in another tab. Choose another name.");
      }
    };
  }

  async create(kind: DocumentKind): Promise<boolean> {
    if (this.pending) return false;
    this.busy = true;
    this.error = null;
    try {
      const document = new DocumentSession(kind, this.recents);
      await document.initialize();
      this.attach(document);
      this.documents = [...this.documents, document];
      this.activeId = document.id;
      return true;
    } catch (e) { this.error = message(e); return false; }
    finally { this.busy = false; }
  }

  private async approveDocuments(documents: DocumentSession[]): Promise<boolean> {
    for (const document of documents) {
      const project = document.projects;
      if (!project.isDirty && project.currentPath !== null) continue;
      const choice = await this.resolveUnsaved(project.fileName ?? `Untitled ${document.kind} coil`);
      if (choice === "cancel") return false;
      if (choice === "save" && !(await this.saveDocument(document))) return false;
      if (choice === "save" && project.isDirty) {
        this.notice = "More edits were made while saving. Review them before continuing.";
        return false;
      }
    }
    return true;
  }

  private async saveDocument(document: DocumentSession): Promise<boolean> {
    const saved = await document.projects.save();
    if (!saved && document.projects.error) this.error = document.projects.error;
    return saved;
  }

  private async approveLeaving(): Promise<boolean> {
    const unsaved = this.documents.filter(d => d.projects.isDirty || d.projects.currentPath === null);
    if (!this.isDirty && unsaved.length === 0) return true;
    const label = unsaved.length ? `${this.label} and ${unsaved.length} unsaved ${unsaved.length === 1 ? "file" : "files"}` : this.label;
    const choice = await this.resolveUnsaved(label);
    if (choice === "cancel") return false;
    if (choice === "save") {
      for (const document of unsaved) if (!(await this.saveDocument(document))) return false;
      if (this.documents.some(d => d.projects.isDirty || d.projects.currentPath === null)) {
        this.notice = "More edits were made while saving. Review them before continuing.";
        return false;
      }
      return await this.writeWorkspace(false);
    }
    return true;
  }

  async close(id: number): Promise<boolean> {
    if (this.pending) return false;
    const document = this.documents.find(d => d.id === id);
    if (!document) return true;
    this.busy = true;
    try {
      if (!(await this.approveDocuments([document]))) return false;
      const index = this.documents.indexOf(document);
      this.documents = this.documents.filter(d => d !== document);
      if (this.activeId === id) this.activeId = this.documents[Math.min(index, this.documents.length - 1)]?.id ?? null;
      return true;
    } finally { this.busy = false; }
  }

  async newProject(): Promise<boolean> {
    if (this.pending) return false;
    this.busy = true;
    try {
      if (!(await this.approveLeaving())) return false;
      this.documents = [];
      this.activeId = null;
      this.path = null;
      this.baseline = "[]";
      this.error = null;
      return true;
    } finally { this.busy = false; }
  }

  async canClose(): Promise<boolean> {
    if (this.pending) return false;
    this.busy = true;
    try { return await this.approveLeaving(); }
    finally { this.busy = false; }
  }

  async open(): Promise<boolean> {
    if (this.pending) return false;
    this.busy = true;
    let path: string | null;
    try { path = await pickProjectOpenPath(); }
    catch (e) { this.error = message(e); return false; }
    finally { this.busy = false; }
    return path !== null && await this.openPath(path);
  }

  private async readDocument(path: string): Promise<DocumentSession> {
    path = await resolveDocumentPath(path);
    const kind = /\.pmsensor$/i.test(path) ? "sensor" : /\.pmmotor$/i.test(path) ? "motor" : null;
    if (!kind) throw new Error("Choose a .pmmotor, .pmsensor, or .pmproj file.");
    const document = new DocumentSession(kind, this.recents);
    await document.initialize();
    if (!(await document.projects.loadFromPath(path))) throw new Error(`${baseName(path)}: ${document.projects.error}`);
    this.attach(document);
    return document;
  }

  async openPath(path: string): Promise<boolean> {
    if (this.pending) return false;
    this.busy = true;
    this.error = null;
    try {
      if (!/\.pmproj$/i.test(path)) {
        path = await resolveDocumentPath(path);
        const existing = this.documents.find(d => d.projects.currentPath === path);
        if (existing) { this.activeId = existing.id; return true; }
        const document = await this.readDocument(path);
        this.documents = [...this.documents, document];
        this.activeId = document.id;
        return true;
      }
      const workspace: WorkspaceLoad = await loadWorkspace(path);
      // Stage every file before replacing the workspace. A missing or corrupt
      // reference leaves all existing tabs and drafts intact.
      const documents: DocumentSession[] = [];
      for (const file of workspace.files) documents.push(await this.readDocument(file));
      if (!(await this.approveLeaving())) return false;
      // Saving the old workspace may have updated files also referenced by
      // the new one. Do not replace just-saved work with a staged older draft.
      const previousPaths = new Set(this.documents.map(d => d.projects.currentPath));
      for (const document of documents) {
        const path = document.projects.currentPath!;
        if (previousPaths.has(path) && !(await document.projects.loadFromPath(path))) {
          throw new Error(document.projects.error ?? `Could not reload ${baseName(path)}.`);
        }
      }
      this.documents = documents;
      this.activeId = documents.find(d => d.projects.currentPath === workspace.active_file)?.id ?? documents[0]?.id ?? null;
      this.path = workspace.path;
      this.baseline = this.fingerprint;
      await this.recents.record(workspace.path).catch(() => undefined);
      return true;
    } catch (e) { this.error = `Open failed: ${message(e)}`; return false; }
    finally { this.busy = false; }
  }

  private async writeWorkspace(saveAs: boolean): Promise<boolean> {
    try {
      // Untitled references cannot be represented in a manifest. Save them
      // first; cancellation leaves the old manifest unchanged.
      for (const d of this.documents) {
        if (d.projects.currentPath === null && !(await this.saveDocument(d))) return false;
      }
      const path = saveAs || !this.path ? await pickWorkspaceSavePath(this.path ?? undefined) : this.path;
      if (!path) return false;
      const fingerprint = this.fingerprint;
      await saveWorkspace(path, this.documents.map(d => d.projects.currentPath!), this.active?.projects.currentPath ?? null);
      this.path = path;
      this.baseline = fingerprint;
      this.notice = `Saved ${baseName(path)}.`;
      await this.recents.record(path).catch(() => undefined);
      return true;
    } catch (e) { this.error = `Could not save project: ${message(e)}`; return false; }
  }

  async save(saveAs = false): Promise<boolean> {
    if (this.pending) return false;
    this.busy = true;
    this.error = null;
    try { return await this.writeWorkspace(saveAs); }
    finally { this.busy = false; }
  }

  async saveAll(): Promise<boolean> {
    if (this.pending) return false;
    this.busy = true;
    this.error = null;
    try {
      for (const d of this.documents) {
        if ((d.projects.isDirty || d.projects.currentPath === null) && !(await this.saveDocument(d))) return false;
      }
      return await this.writeWorkspace(false);
    } finally { this.busy = false; }
  }
}
