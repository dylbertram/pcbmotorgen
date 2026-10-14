<script lang="ts">
  import { onMount, tick } from "svelte";
  import { ContextMenu, Dialog } from "bits-ui";
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import { invoke } from "@tauri-apps/api/core";
  import { listen } from "@tauri-apps/api/event";
  import DocumentEditor from "./DocumentEditor.svelte";
  import NewFileDialog from "./lib/components/layout/NewFileDialog.svelte";
  import ProjectControls from "./lib/components/layout/ProjectControls.svelte";
  import { WorkspaceStore, type DocumentSession, type UnsavedChoice } from "./lib/stores/workspace.svelte";
  import type { ProjectStore } from "./lib/stores/project.svelte";
  import { recentFiles } from "./lib/stores/recentFiles.svelte";
  import { bindProjectMenuActions, isTauriAvailable, revealInFinder } from "./lib/ipc";
  import type { DocumentKind } from "./lib/types";
  import PreferencesDialog from "./lib/components/layout/PreferencesDialog.svelte";
  import { ConfigStore } from "./lib/stores/config.svelte";

  let unsaved = $state<{ label: string; resolve: (choice: UnsavedChoice) => void } | null>(null);
  const workspace = new WorkspaceStore(recentFiles, (label) => new Promise(resolve => { unsaved = { label, resolve }; }));
  let newFileOpen = $state(false);
  let recentLoading = $state(true);
  let editor = $state<DocumentEditor | undefined>();
  let preferencesConfig = $state.raw<ConfigStore | null>(null);
  let renameTarget = $state<ProjectStore | null>(null);
  let openPaths = $derived(
    workspace.documents
      .map((d) => d.projects.currentPath)
      .filter((p): p is string => p !== null),
  );
  const button = "rounded px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400 disabled:opacity-50";
  const item = "cursor-pointer rounded px-3 py-2 text-xs outline-none data-[highlighted]:bg-slate-700 data-[disabled]:opacity-40";

  function decide(choice: UnsavedChoice): void {
    const pending = unsaved;
    unsaved = null;
    pending?.resolve(choice);
  }

  async function create(kind: DocumentKind): Promise<void> {
    if (await workspace.create(kind)) newFileOpen = false;
  }

  async function openFromDialog(path: string): Promise<void> {
    if (await workspace.openPath(path)) newFileOpen = false;
  }

  async function openTabVersions(document: DocumentSession, creating: boolean): Promise<void> {
    if (workspace.pending) return;
    workspace.activate(document.id);
    await tick();
    editor?.openVersions(creating);
  }

  async function revealTabFile(document: DocumentSession): Promise<void> {
    const path = document.projects.currentPath;
    if (!path || workspace.pending) return;
    try {
      await revealInFinder(path);
    } catch (e) {
      workspace.error = e instanceof Error ? e.message : String(e);
    }
  }

  function action(name: string): void {
    if (workspace.pending) return;
    if (name === "settings" && !workspace.active) preferencesConfig = new ConfigStore();
    else editor?.handleAction(name);
  }

  async function fileTabKeydown(event: KeyboardEvent, id: number): Promise<void> {
    const count = workspace.documents.length;
    const index = workspace.documents.findIndex(d => d.id === id);
    const target = event.key === "ArrowRight" ? (index + 1) % count
      : event.key === "ArrowLeft" ? (index + count - 1) % count
      : event.key === "Home" ? 0 : event.key === "End" ? count - 1 : null;
    if (target === null || workspace.pending) return;
    event.preventDefault();
    const nextId = workspace.documents[target].id;
    workspace.activate(nextId);
    await tick();
    document.getElementById(`file-tab-${nextId}`)?.focus();
  }
  function saveFile(saveAs = false): void {
    if (workspace.pending) return;
    if (workspace.active) void workspace.active.projects.save(saveAs);
    else void workspace.save(saveAs);
  }

  async function approveQuit(): Promise<void> {
    try {
      if (await workspace.canClose()) await invoke("quit_app");
    } catch (e) { workspace.error = e instanceof Error ? e.message : String(e); }
  }

  $effect(() => {
    const id = workspace.activeId;
    if (id !== null) document.getElementById(`file-tab-${id}`)?.scrollIntoView({ block: "nearest", inline: "nearest" });
  });

  onMount(() => {
    void recentFiles.load().finally(() => (recentLoading = false));
    const unbind = bindProjectMenuActions({
      newFile: () => { if (!workspace.pending) newFileOpen = true; },
      newProject: () => { void workspace.newProject(); },
      open: () => { void workspace.open(); },
      save: () => saveFile(), saveAs: () => saveFile(true),
      saveWorkspace: () => { void workspace.save(); },
      saveWorkspaceAs: () => { void workspace.save(true); },
      saveAll: () => { void workspace.saveAll(); },
      closeFile: () => { if (workspace.activeId !== null) void workspace.close(workspace.activeId); },
      saveNewVersion: () => action("versions"),
      exportDxf: () => action("export"), sendKicad: () => action("kicad"),
      importCad: () => action("import"), settings: () => action("settings"),
      openRecent: (path) => { void workspace.openPath(path); },
      clearRecent: () => { void recentFiles.clear(); },
    });
    const unclose = isTauriAvailable() ? getCurrentWindow().onCloseRequested(async (event) => {
      event.preventDefault();
      await approveQuit();
    }) : Promise.resolve(() => {});
    const unquit = isTauriAvailable() ? listen("app:request-quit", () => { void approveQuit(); }) : Promise.resolve(() => {});
    return () => { void unbind.then(f => f()); void unclose.then(f => f()); void unquit.then(f => f()); };
  });
</script>

<main class="flex min-h-screen flex-col bg-slate-900 text-slate-100 lg:h-screen lg:overflow-hidden">
  <header class="shrink-0 border-b border-slate-700 bg-slate-950/60">
    <nav class="flex min-h-10 items-stretch overflow-x-auto pl-[95px]" aria-label="Open files" data-tauri-drag-region>
      <div role="tablist" aria-label="Coil files" class="flex items-stretch">
      {#each workspace.documents as document (document.id)}
        {@const tabTitle = document.projects.fileName ?? `Untitled ${document.kind} ${document.id}`}
        <ContextMenu.Root>
          <ContextMenu.Trigger class="flex shrink-0 items-center gap-1 border-r border-slate-700 border-t-2 pr-1 {workspace.activeId === document.id ? 'border-t-emerald-400 bg-slate-800' : 'border-t-transparent bg-slate-950/30'}">
            <button type="button" role="tab" id={`file-tab-${document.id}`} aria-controls="active-document" aria-selected={workspace.activeId === document.id} tabindex={workspace.activeId === document.id ? 0 : -1} onkeydown={(event) => void fileTabKeydown(event, document.id)} class="flex items-center gap-2 px-3 py-2 text-xs focus-visible:outline focus-visible:outline-emerald-400 disabled:opacity-50" disabled={workspace.pending} title={document.projects.currentPath ?? document.projects.defaultFileName} onclick={() => workspace.activate(document.id)}>
              <span class={document.kind === "motor" ? "text-emerald-300" : "text-sky-300"}>{document.kind === "motor" ? "M" : "S"}</span>
              <span>{tabTitle}</span>
              {#if document.projects.isDirty || document.projects.currentPath === null}<span class="text-amber-300" aria-label={document.projects.isDirty ? "Unsaved changes" : "Unsaved file"}>●</span>{/if}
            </button>
            <button
              type="button"
              onclick={() => void openTabVersions(document, false)}
              disabled={workspace.pending}
              aria-label={workspace.activeId === document.id || workspace.documents.length === 1 ? "Project versions" : `Project versions for ${tabTitle}`}
              class="shrink-0 rounded border border-slate-700 bg-slate-900/70 px-1.5 py-0.5 text-[10px] text-slate-300 hover:border-emerald-500/50 hover:text-emerald-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400 disabled:opacity-50"
            >
              {document.projects.activeVersionId !== null ? `Version ${document.projects.activeVersionId}` : "Versions"}
            </button>
            <button type="button" class="rounded px-1.5 py-0.5 text-slate-500 hover:bg-slate-700 hover:text-slate-100 focus-visible:outline focus-visible:outline-emerald-400 disabled:opacity-50" disabled={workspace.pending} aria-label={`Close ${tabTitle}`} onclick={() => void workspace.close(document.id)}>×</button>
          </ContextMenu.Trigger>
          <ContextMenu.Portal>
            <ContextMenu.Content
              preventScroll={false}
              onCloseAutoFocus={(event) => { if (renameTarget) event.preventDefault(); }}
              class="z-[150] min-w-44 rounded-lg border border-slate-600 bg-slate-800 p-1 text-slate-100 shadow-xl"
            >
              <ContextMenu.Item class={item} disabled={workspace.pending} onSelect={() => { renameTarget = document.projects; }}>Rename</ContextMenu.Item>
              <ContextMenu.Item class={item} disabled={workspace.pending || !document.projects.currentPath} onSelect={() => { void revealTabFile(document); }}>Reveal in Finder</ContextMenu.Item>
              <ContextMenu.Item class={item} disabled={workspace.pending} onSelect={() => { void document.projects.save(false); }}>Save</ContextMenu.Item>
              <ContextMenu.Item class={item} disabled={workspace.pending} onSelect={() => { void openTabVersions(document, true); }}>Save new version</ContextMenu.Item>
              <ContextMenu.Separator class="my-1 h-px bg-slate-600" />
              <ContextMenu.Item class={item} disabled={workspace.pending} onSelect={() => { void workspace.close(document.id); }}>Close</ContextMenu.Item>
            </ContextMenu.Content>
          </ContextMenu.Portal>
        </ContextMenu.Root>
      {/each}
      </div>
      <button type="button" class="shrink-0 px-4 py-2 text-slate-400 hover:bg-slate-800 focus-visible:outline focus-visible:outline-emerald-400 disabled:opacity-50" disabled={workspace.pending} aria-label="New coil file" onclick={() => (newFileOpen = true)}>+</button>
    </nav>
  </header>

  {#if workspace.error}
    <div role="alert" class="flex shrink-0 items-start justify-between gap-3 border-b border-rose-500/40 bg-rose-500/10 px-5 py-3 text-sm text-rose-200"><p>{workspace.error}</p><button type="button" class="underline" onclick={() => (workspace.error = null)}>Dismiss</button></div>
  {/if}
  {#if workspace.notice}
    <div role="status" class="flex shrink-0 justify-between px-5 py-2 text-xs text-emerald-300"><p>{workspace.notice}</p><button type="button" class="underline" onclick={() => (workspace.notice = null)}>Dismiss</button></div>
  {/if}

  {#if workspace.active}
    {#key workspace.active.id}
      <div id="active-document" role="tabpanel" aria-labelledby={`file-tab-${workspace.active.id}`} inert={workspace.busy} aria-busy={workspace.busy} class="flex min-h-0 flex-1 flex-col">
        <DocumentEditor session={workspace.active} active bind:this={editor} />
      </div>
    {/key}
  {:else}
    <section class="mx-auto w-full max-w-3xl flex-1 overflow-y-auto px-6 py-16" aria-label="Project workspace">
      <h1 class="text-2xl font-semibold">{workspace.label}</h1>
      <p class="mt-3 max-w-lg text-sm leading-relaxed text-slate-400">Keep motor and sensor coil files together in a project. Each file has its own saved versions.</p>
      <div class="mt-6 flex gap-3">
        <button type="button" disabled={workspace.pending} onclick={() => (newFileOpen = true)} class="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500 focus-visible:outline focus-visible:outline-emerald-300 disabled:opacity-50">New coil file</button>
        <button type="button" disabled={workspace.pending} onclick={() => void workspace.open()} class="rounded-md border border-slate-600 px-4 py-2 text-sm hover:bg-slate-800 focus-visible:outline focus-visible:outline-emerald-300 disabled:opacity-50">Open file or project…</button>
      </div>
      <h2 class="mt-12 text-sm font-medium text-slate-300">Recent files and projects</h2>
      {#if recentLoading}<p class="mt-3 text-xs text-slate-500">Loading…</p>
      {:else if recentFiles.paths.length === 0}<p class="mt-3 text-xs text-slate-500">Saved files and projects will appear here.</p>
      {:else}<ul class="mt-3 divide-y divide-slate-800">
        {#each recentFiles.paths as path (path)}
          <li><button type="button" disabled={workspace.pending} onclick={() => void workspace.openPath(path)} class="w-full rounded px-2 py-3 text-left hover:bg-slate-800 focus-visible:outline focus-visible:outline-emerald-400 disabled:opacity-50"><span class="block text-sm text-slate-200">{path.split(/[\\/]/).pop()}</span><span class="mt-1 block truncate text-xs text-slate-500">{path}</span></button></li>
        {/each}
      </ul>{/if}
    </section>
  {/if}

  {#if newFileOpen}
    <NewFileDialog
      busy={workspace.pending}
      directories={workspace.directories}
      {openPaths}
      onCreate={(kind) => void create(kind)}
      onOpenFile={(path) => void openFromDialog(path)}
      onClose={() => (newFileOpen = false)}
    />
  {/if}
  {#if renameTarget}
    <ProjectControls projects={renameTarget} onClose={() => (renameTarget = null)} />
  {/if}
  {#if preferencesConfig}<PreferencesDialog config={preferencesConfig} disabled={workspace.pending} onClose={() => (preferencesConfig = null)} />{/if}

  <Dialog.Root open={unsaved !== null} onOpenChange={(open) => { if (!open) decide("cancel"); }}>
    <Dialog.Portal>
      <Dialog.Overlay class="fixed inset-0 z-[150] bg-slate-950/80" />
      <Dialog.Content class="fixed left-1/2 top-1/2 z-[151] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-slate-600 bg-slate-900 p-6 text-slate-100 shadow-xl focus:outline-none">
        <Dialog.Title class="text-lg font-semibold">Save changes?</Dialog.Title>
        <Dialog.Description class="mt-2 break-words text-sm text-slate-400">Save changes to {unsaved?.label} before continuing?</Dialog.Description>
        <div class="mt-6 flex flex-wrap justify-end gap-2">
          <button type="button" class={button} onclick={() => decide("cancel")}>Cancel</button>
          <button type="button" class={button} onclick={() => decide("discard")}>Discard</button>
          <button type="button" class="rounded bg-emerald-600 px-4 py-2 text-sm hover:bg-emerald-500 focus-visible:outline focus-visible:outline-emerald-300" onclick={() => decide("save")}>Save</button>
        </div>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
</main>
