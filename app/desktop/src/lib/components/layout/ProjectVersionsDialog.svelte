<script lang="ts">
  import { Dialog } from "bits-ui";
  import { untrack } from "svelte";
  import { confirm } from "@tauri-apps/plugin-dialog";
  import { isTauriAvailable } from "../../ipc/core";
  import type { ProjectStore } from "../../stores/project.svelte";
  import { attachBackdropScrollGuard, lockPageScroll } from "../../utils/pageScrollLock";

  let { projects, creating = false, onClose }: {
    projects: ProjectStore;
    creating?: boolean;
    onClose: () => void;
  } = $props();

  let open = $state(true);
  let newVersion = $state(untrack(() => creating));
  let selectedId = $state(untrack(() => projects.activeVersionId));
  let description = $state(untrack(() => creating ? "" : projects.activeVersion?.description ?? ""));
  let selected = $derived(projects.versions.find((v) => v.id === selectedId) ?? null);
  let backdropRef = $state<HTMLDivElement | null>(null);
  let panelRef = $state<HTMLDivElement | null>(null);
  let orderedVersions = $derived([...projects.versions].sort((a, b) => b.last_edited_at_unix_ms - a.last_edited_at_unix_ms || b.id - a.id));

  $effect(() => {
    if (!backdropRef) return;
    const detach = attachBackdropScrollGuard(backdropRef, panelRef);
    const unlock = lockPageScroll(document);
    return () => { detach(); unlock(); };
  });

  function selectVersion(id: number): void {
    selectedId = id;
    newVersion = false;
    description = projects.versions.find((v) => v.id === id)?.description ?? "";
  }

  function startVersion(): void {
    newVersion = true;
    description = "";
  }

  function date(value: number): string {
    return new Date(value).toLocaleString();
  }

  async function saveDescription(): Promise<void> {
    if (selectedId !== null) await projects.describeVersion(selectedId, description.trim());
  }

  async function saveNewVersion(): Promise<void> {
    if (await projects.save(false, true, description.trim())) onClose();
  }

  async function openVersion(): Promise<void> {
    if (selectedId !== null && await projects.openVersion(selectedId)) onClose();
  }

  async function deleteVersion(): Promise<void> {
    if (selectedId === null || projects.busy) return;
    const id = selectedId;
    const message = `Delete version ${id} from this project file? This cannot be undone.${id === projects.activeVersionId ? " The most recently edited remaining version will open, and any unsaved edits to this version will be discarded." : ""}`;
    const accepted = isTauriAvailable()
      ? await confirm(message, { title: "Delete version", kind: "warning", okLabel: "Delete version", cancelLabel: "Keep version" })
      : window.confirm(message);
    if (accepted && await projects.deleteVersion(id)) {
      selectVersion(projects.activeVersionId ?? projects.versions[0].id);
    }
  }
</script>

<Dialog.Root bind:open onOpenChange={(value) => { if (!value && !projects.busy) onClose(); }}>
  <Dialog.Portal>
    <Dialog.Overlay bind:ref={backdropRef} class="fixed inset-0 z-[121] bg-slate-950/80 backdrop-blur-sm" />
    <Dialog.Content
      bind:ref={panelRef}
      preventScroll={false}
      onEscapeKeydown={(event) => { if (projects.busy) event.preventDefault(); }}
      onInteractOutside={(event) => { if (projects.busy) event.preventDefault(); }}
      class="fixed left-1/2 top-1/2 z-[121] flex h-[min(580px,calc(100dvh-2rem))] w-[calc(100%-2rem)] max-w-3xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900 text-slate-100 shadow-2xl"
    >
      <header class="flex shrink-0 items-start justify-between gap-4 border-b border-slate-700 px-5 py-4">
        <div class="min-w-0">
          <Dialog.Title class="text-base font-semibold">Project versions</Dialog.Title>
          <Dialog.Description class="mt-1 text-xs text-slate-400">All versions stay in {projects.fileName ?? "one project file"}. Opening a file loads its most recently edited version.</Dialog.Description>
        </div>
        <Dialog.Close disabled={projects.busy} aria-label="Close project versions" class="rounded px-2 py-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100 disabled:opacity-50">×</Dialog.Close>
      </header>

      <div class="grid min-h-0 flex-1 grid-rows-[minmax(120px,0.7fr)_minmax(0,1.3fr)] overflow-hidden sm:grid-cols-[minmax(180px,0.8fr)_minmax(0,1.2fr)] sm:grid-rows-1">
        <aside class="min-h-0 overflow-y-auto overscroll-contain border-b border-slate-700 bg-slate-950/40 p-3 sm:border-b-0 sm:border-r" aria-label="Saved versions">
          <button type="button" onclick={startVersion} disabled={projects.busy} class="mb-3 w-full rounded-md border border-emerald-500/40 px-3 py-2 text-left text-xs font-medium text-emerald-200 hover:bg-emerald-500/10 disabled:opacity-50">Save new version…</button>
          {#if orderedVersions.length === 0}
            <p class="px-2 py-3 text-xs text-slate-400">No saved versions yet. Save the design to create the first version.</p>
          {:else}
            <ul class="space-y-1">
              {#each orderedVersions as version (version.id)}
                <li>
                  <button type="button" onclick={() => selectVersion(version.id)} disabled={projects.busy} aria-pressed={!newVersion && selectedId === version.id} class="w-full rounded-md px-3 py-3 text-left disabled:opacity-50 {!newVersion && selectedId === version.id ? 'bg-slate-800 ring-1 ring-emerald-500/50' : 'hover:bg-slate-800/60'}">
                    <span class="flex items-center justify-between gap-2 text-sm font-medium">Version {version.id}{#if projects.activeVersionId === version.id}<span class="text-[10px] font-normal text-emerald-300">Current</span>{/if}</span>
                    <span class="mt-1 block truncate text-xs text-slate-400">{version.description || "No description"}</span>
                    <span class="mt-1 block text-[10px] text-slate-500">Edited {date(version.last_edited_at_unix_ms)}</span>
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
        </aside>

        <section class="min-h-0 min-w-0 overflow-y-auto overscroll-contain p-5" aria-label="Version details">
          <h3 class="text-sm font-semibold">{newVersion ? "Save new version" : selected ? `Version ${selected.id}` : "Version details"}</h3>
          {#if newVersion}
            <p class="mt-2 text-xs leading-relaxed text-slate-400">Save the current design, including unsaved edits, as a separate version. Existing versions will not change.</p>
          {:else if selected}
            <dl class="mt-3 space-y-2 text-xs">
              <div class="flex flex-wrap justify-between gap-2"><dt class="text-slate-400">Created</dt><dd><time datetime={new Date(selected.created_at_unix_ms).toISOString()}>{date(selected.created_at_unix_ms)}</time></dd></div>
              <div class="flex flex-wrap justify-between gap-2"><dt class="text-slate-400">Last edited</dt><dd><time datetime={new Date(selected.last_edited_at_unix_ms).toISOString()}>{date(selected.last_edited_at_unix_ms)}</time></dd></div>
            </dl>
          {/if}
          {#if newVersion || selected}
            <label class="mt-5 block text-xs font-medium text-slate-300" for="version-description">Description</label>
            <textarea id="version-description" bind:value={description} disabled={projects.busy} rows="4" placeholder="What changed in this version?" class="mt-2 w-full resize-y rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none disabled:opacity-50"></textarea>
            {#if !newVersion}
              <div class="mt-3 flex flex-wrap gap-2">
                <button type="button" onclick={saveDescription} disabled={projects.busy || description.trim() === selected?.description} class="rounded-md border border-slate-600 px-3 py-2 text-xs hover:bg-slate-800 disabled:opacity-50">Save description</button>
                <button type="button" onclick={deleteVersion} disabled={projects.busy || projects.versions.length <= 1} class="rounded-md border border-rose-500/40 px-3 py-2 text-xs text-rose-300 hover:bg-rose-500/10 disabled:opacity-50">Delete version</button>
              </div>
              {#if projects.versions.length <= 1}<p class="mt-2 text-[11px] text-slate-500">Keep at least one version in the file.</p>{/if}
            {/if}
          {/if}
          {#if projects.error}<p role="alert" class="mt-4 rounded-md border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-200">{projects.error}</p>{/if}
        </section>
      </div>

      <footer class="flex shrink-0 items-center justify-between border-t border-slate-700 px-5 py-3">
        <Dialog.Close disabled={projects.busy} class="rounded-md px-3 py-2 text-xs text-slate-400 hover:bg-slate-800 disabled:opacity-50">Close</Dialog.Close>
        {#if newVersion}
          <button type="button" onclick={saveNewVersion} disabled={projects.busy} class="rounded-md border border-emerald-500/40 bg-emerald-600/20 px-4 py-2 text-xs font-medium text-emerald-200 hover:bg-emerald-600/30 disabled:opacity-50">{projects.busy ? "Saving…" : "Save new version"}</button>
        {:else if selected}
          <button type="button" onclick={openVersion} disabled={projects.busy || selectedId === projects.activeVersionId} class="rounded-md border border-emerald-500/40 bg-emerald-600/20 px-4 py-2 text-xs font-medium text-emerald-200 hover:bg-emerald-600/30 disabled:opacity-50">Open version</button>
        {/if}
      </footer>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
