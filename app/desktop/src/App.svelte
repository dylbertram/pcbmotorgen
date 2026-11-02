<script lang="ts">
  import { onMount, tick, untrack } from "svelte";
  import { Dialog } from "bits-ui";
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import { invoke } from "@tauri-apps/api/core";
  import { listen } from "@tauri-apps/api/event";
  import DocumentEditor from "./DocumentEditor.svelte";
  import NewFileDialog from "./lib/components/layout/NewFileDialog.svelte";
  import ProjectControls from "./lib/components/layout/ProjectControls.svelte";
  import FileTabs from "./lib/components/layout/FileTabs.svelte";
  import EditorSplit from "./lib/components/layout/EditorSplit.svelte";
  import { WorkspaceStore, type DocumentSession, type UnsavedChoice } from "./lib/stores/workspace.svelte";
  import { EditorGroups, type EditorSide } from "./lib/stores/editorGroups.svelte";
  import type { ProjectStore } from "./lib/stores/project.svelte";
  import { recentFiles } from "./lib/stores/recentFiles.svelte";
  import { bindProjectMenuActions, isTauriAvailable, revealInFinder } from "./lib/ipc";
  import type { DocumentKind } from "./lib/types";
  import PreferencesDialog from "./lib/components/layout/PreferencesDialog.svelte";
  import { ConfigStore } from "./lib/stores/config.svelte";
  import { bindDriverImports, openDriverCalculator } from "./lib/driverCalculatorWindow";

  let unsaved = $state<{ label: string; resolve: (choice: UnsavedChoice) => void } | null>(null);
  const workspace = new WorkspaceStore(recentFiles, label => new Promise(resolve => { unsaved = { label, resolve }; }));
  const groups = new EditorGroups();
  let newFileOpen = $state(false);
  let recentLoading = $state(true);
  let editors = $state<Partial<Record<EditorSide, DocumentEditor>>>({});
  const editor = $derived(editors[groups.focusedGroup]);
  let preferencesConfig = $state.raw<ConfigStore | null>(null);
  let renameTarget = $state<ProjectStore | null>(null);
  let drag = $state<{ id: number; side: EditorSide } | null>(null);
  let dropTarget = $state<EditorSide | null>(null);
  let openingCalculator = false;
  const blocked = $derived(!!(newFileOpen || unsaved || renameTarget || preferencesConfig || workspace.busy));
  const openPaths = $derived(workspace.documents.map(d => d.projects.currentPath).filter((p): p is string => p !== null));
  const button = "rounded px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400 disabled:opacity-50";

  $effect(() => {
    const documents = workspace.documents, id = workspace.activeId;
    untrack(() => groups.sync(documents, id));
  });
  $effect(() => {
    const id = workspace.activeId, side = groups.focusedGroup;
    if (id !== null) document.getElementById(`file-tab-${side}-${id}`)?.scrollIntoView({ block: "nearest", inline: "nearest" });
  });
  function focus(side: EditorSide): void {
    if (workspace.pending || blocked) return;
    groups.focusedGroup = side;
    const id = groups.selected(side);
    if (id !== null) workspace.activate(id);
  }
  function select(side: EditorSide, id: number): void {
    groups.select(side, id);
    workspace.activate(id);
  }
  function split(id: number): void {
    if (workspace.pending) return;
    groups.splitRight(id);
    workspace.activate(id);
  }
  async function closeView(side: EditorSide, id: number): Promise<void> {
    if (workspace.pending) return;
    const other = side === "left" ? "right" : "left";
    if (groups.tabs(other).includes(id)) groups.removeView(id, side);
    else if (!(await workspace.close(id))) return;
    groups.sync(workspace.documents, null);
    const next = groups.selected(groups.focusedGroup);
    if (next !== null) workspace.activate(next);
  }
  function dragOver(event: DragEvent, side: EditorSide): void {
    if (!drag || workspace.pending || blocked) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
    const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
    dropTarget = groups.splitOpen ? side : event.clientX > box.x + box.width * .55 ? "right" : "left";
  }
  function drop(event: DragEvent): void {
    if (!drag || !dropTarget || workspace.pending) return;
    event.preventDefault();
    const { id, side } = drag, target = dropTarget;
    if (!groups.splitOpen && target === "right" && groups.left.length === 1) groups.splitRight(id);
    else groups.move(id, side, target);
    workspace.activate(id);
    drag = null; dropTarget = null;
  }
  function decide(choice: UnsavedChoice): void { const pending = unsaved; unsaved = null; pending?.resolve(choice); }
  async function create(kind: DocumentKind, source: "generator" | "import"): Promise<void> {
    if (!(await workspace.create(kind))) return;
    newFileOpen = false;
    if (source === "import") { await tick(); editor?.handleAction("import"); }
  }
  async function openFromDialog(path: string): Promise<void> { if (await workspace.openPath(path)) newFileOpen = false; }
  async function openTabVersions(source: DocumentSession, side: EditorSide, creating: boolean): Promise<void> {
    if (workspace.pending) return;
    select(side, source.id); await tick(); editor?.openVersions(creating);
  }
  async function revealTabFile(source: DocumentSession): Promise<void> {
    const path = source.projects.currentPath;
    if (!path || workspace.pending) return;
    try { await revealInFinder(path); } catch (e) { workspace.error = e instanceof Error ? e.message : String(e); }
  }
  function action(name: string): void {
    if (workspace.pending) return;
    if (name === "settings" && !workspace.active) preferencesConfig = new ConfigStore();
    else editor?.handleAction(name);
  }
  function saveFile(saveAs = false): void {
    if (workspace.pending) return;
    if (workspace.active) void workspace.active.projects.save(saveAs);
    else void workspace.save(saveAs);
  }
  async function calculator(): Promise<void> {
    if (openingCalculator) return;
    openingCalculator = true;
    try {
      let snapshot = null;
      try { snapshot = await editor?.driverCalculatorSnapshot() ?? null; }
      catch (e) { workspace.notice = `Calculator opened without motor data: ${e instanceof Error ? e.message : String(e)}`; }
      await openDriverCalculator(snapshot);
    }
    catch (e) { workspace.error = e instanceof Error ? e.message : String(e); }
    finally { openingCalculator = false; }
  }
  async function approveQuit(): Promise<void> {
    try { if (await workspace.canClose()) await invoke("quit_app"); }
    catch (e) { workspace.error = e instanceof Error ? e.message : String(e); }
  }
  onMount(() => {
    void recentFiles.load().then(async () => {
      const last = recentFiles.paths[0];
      if (last && !workspace.pending && !workspace.documents.length) await workspace.openPath(last);
    }).catch(() => undefined).finally(() => (recentLoading = false));
    const unbind = bindProjectMenuActions({
      simulate: command => { if (!workspace.pending) { if (command === "driver") void calculator(); else editor?.handleSimulationAction(command); } },
      newFile: () => { if (!workspace.pending) newFileOpen = true; }, newProject: () => { void workspace.newProject(); },
      open: () => { void workspace.open(); }, save: () => saveFile(), saveAs: () => saveFile(true),
      saveWorkspace: () => { void workspace.save(); }, saveWorkspaceAs: () => { void workspace.save(true); }, saveAll: () => { void workspace.saveAll(); },
      closeFile: () => { const id = groups.selected(groups.focusedGroup); if (id !== null) void closeView(groups.focusedGroup, id); },
      saveNewVersion: () => action("versions"), exportDxf: () => action("export"), sendKicad: () => action("kicad"),
      importCad: () => action("import"), settings: () => action("settings"),
      openRecent: path => { void workspace.openPath(path); }, clearRecent: () => { void recentFiles.clear(); },
    });
    const unimports = bindDriverImports(() => editor?.driverCalculatorSnapshot() ?? null);
    const unclose = isTauriAvailable() ? getCurrentWindow().onCloseRequested(async event => { event.preventDefault(); await approveQuit(); }) : Promise.resolve(() => {});
    const unquit = isTauriAvailable() ? listen("app:request-quit", () => { void approveQuit(); }) : Promise.resolve(() => {});
    return () => { void unbind.then(f => f()); void unimports.then(f => f()); void unclose.then(f => f()); void unquit.then(f => f()); };
  });
</script>

{#snippet group(side: EditorSide)}
  {@const ids = groups.tabs(side)}
  {@const source = workspace.documents.find(d => d.id === groups.selected(side))}
  <section aria-label={side === "left" ? "Left editor group" : "Right editor group"} class="relative flex min-h-0 min-w-0 flex-1 flex-col"
    onpointerdowncapture={() => focus(side)} onfocusincapture={() => focus(side)}
    ondragover={event => dragOver(event, side)} ondrop={drop}
    ondragleave={event => { if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) dropTarget = null; }}>
    <FileTabs documents={ids.map(id => workspace.documents.find(d => d.id === id)!).filter(Boolean)} selected={groups.selected(side)} {side} busy={workspace.pending}
      onSelect={id => select(side, id)} onClose={id => void closeView(side, id)} onVersions={(source, creating) => void openTabVersions(source, side, creating)}
      onRename={source => { renameTarget = source.projects; }} onReveal={source => void revealTabFile(source)} onNew={() => { focus(side); newFileOpen = true; }} onSplit={split}
      onDrag={(id, side) => { drag = { id, side }; }} onDragEnd={() => { drag = null; dropTarget = null; }} />
    {#if source}
      {#key source.id}
        <div id={`document-${side}-${source.id}`} role="tabpanel" aria-labelledby={`file-tab-${side}-${source.id}`} inert={workspace.busy} aria-busy={workspace.busy} class="flex min-h-0 flex-1 flex-col">
          <DocumentEditor session={source} view={groups.view(source, side)} active={!blocked} focused={groups.focusedGroup === side} onOpenDriverCalculator={() => void calculator()}
            bind:this={() => editors[side], value => { editors[side] = value; }} />
        </div>
      {/key}
    {/if}
    {#if drag && dropTarget && (dropTarget === side || !groups.splitOpen)}
      <div data-testid="editor-drop-preview" aria-hidden="true" class="pointer-events-none absolute top-10 bottom-0 z-50 rounded border-2 border-sky-400/70 bg-sky-400/20"
        style:left={!groups.splitOpen && dropTarget === "right" ? "50%" : "0"} style:right={!groups.splitOpen && dropTarget === "left" ? "50%" : "0"}></div>
    {/if}
  </section>
{/snippet}

<main class="flex h-dvh min-h-0 flex-col overflow-hidden bg-slate-900 text-slate-100">
  {#if workspace.error}<div role="alert" class="flex shrink-0 items-start justify-between gap-3 border-b border-rose-500/40 bg-rose-500/10 px-5 py-3 text-sm text-rose-200"><p>{workspace.error}</p><button type="button" class="underline" onclick={() => workspace.error = null}>Dismiss</button></div>{/if}
  {#if workspace.notice}<div role="status" class="flex shrink-0 justify-between px-5 py-2 text-xs text-emerald-300"><p>{workspace.notice}</p><button type="button" class="underline" onclick={() => workspace.notice = null}>Dismiss</button></div>{/if}
  {#if workspace.documents.length}
    <EditorSplit state={groups}>
      {#snippet left()}{@render group("left")}{/snippet}
      {#snippet right()}{@render group("right")}{/snippet}
    </EditorSplit>
  {:else}
    <header class="flex min-h-10 shrink-0 border-b border-slate-700 pl-[95px]" data-tauri-drag-region><button type="button" class={button} aria-label="New coil file" onclick={() => newFileOpen = true}>+</button></header>
    <section class="mx-auto w-full max-w-3xl flex-1 overflow-y-auto px-6 py-16" aria-label="Project workspace">
      <h1 class="text-2xl font-semibold">{workspace.label}</h1>
      <p class="mt-3 max-w-lg text-sm leading-relaxed text-slate-400">Keep motor and sensor coil files together in a project. Each file has its own saved versions.</p>
      <div class="mt-6 flex gap-3">
        <button type="button" disabled={workspace.pending} onclick={() => newFileOpen = true} class="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500 focus-visible:outline focus-visible:outline-emerald-300">New coil file</button>
        <button type="button" disabled={workspace.pending} onclick={() => void workspace.open()} class="rounded-md border border-slate-600 px-4 py-2 text-sm hover:bg-slate-800 focus-visible:outline focus-visible:outline-emerald-300">Open file or project…</button>
      </div>
      <h2 class="mt-12 text-sm font-medium text-slate-300">Recent files and projects</h2>
      {#if recentLoading}<p class="mt-3 text-xs text-slate-500">Loading…</p>
      {:else if !recentFiles.paths.length}<p class="mt-3 text-xs text-slate-500">Saved files and projects will appear here.</p>
      {:else}<ul class="mt-3 divide-y divide-slate-800">{#each recentFiles.paths as path (path)}<li><button type="button" disabled={workspace.pending} onclick={() => void workspace.openPath(path)} class="w-full rounded px-2 py-3 text-left hover:bg-slate-800 focus-visible:outline focus-visible:outline-emerald-400"><span class="block text-sm text-slate-200">{path.split(/[\\/]/).pop()}</span><span class="mt-1 block truncate text-xs text-slate-500">{path}</span></button></li>{/each}</ul>{/if}
    </section>
  {/if}
  {#if newFileOpen}<NewFileDialog busy={workspace.pending} directories={workspace.directories} {openPaths} onCreate={(kind, source) => void create(kind, source)} onOpenFile={path => void openFromDialog(path)} onClose={() => newFileOpen = false} />{/if}
  {#if renameTarget}<ProjectControls projects={renameTarget} onClose={() => renameTarget = null} />{/if}
  {#if preferencesConfig}<PreferencesDialog config={preferencesConfig} disabled={workspace.pending} onClose={() => preferencesConfig = null} />{/if}
  <Dialog.Root open={unsaved !== null} onOpenChange={open => { if (!open) decide("cancel"); }}>
    <Dialog.Portal>
      <Dialog.Overlay class="fixed inset-0 z-[150] bg-slate-950/80" />
      <Dialog.Content class="fixed left-1/2 top-1/2 z-[151] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-slate-600 bg-slate-900 p-6 text-slate-100 shadow-xl focus:outline-none">
        <Dialog.Title class="text-lg font-semibold">Save changes?</Dialog.Title>
        <Dialog.Description class="mt-2 break-words text-sm text-slate-400">Save changes to {unsaved?.label} before continuing?</Dialog.Description>
        <div class="mt-6 flex flex-wrap justify-end gap-2"><button type="button" class={button} onclick={() => decide("cancel")}>Cancel</button><button type="button" class={button} onclick={() => decide("discard")}>Discard</button><button type="button" class="rounded bg-emerald-600 px-4 py-2 text-sm hover:bg-emerald-500 focus-visible:outline focus-visible:outline-emerald-300" onclick={() => decide("save")}>Save</button></div>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
</main>
