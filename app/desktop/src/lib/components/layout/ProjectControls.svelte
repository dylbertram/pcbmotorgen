<script lang="ts">
  import { Dialog } from "bits-ui";
  import { untrack } from "svelte";
  import { pickProjectDirectory } from "../../ipc/project";
  import type { ProjectStore } from "../../stores/project.svelte";

  let { projects, onClose }: { projects: ProjectStore; onClose: () => void } = $props();
  let open = $state(true);
  let name = $state(untrack(() => projects.fileName ?? projects.defaultFileName));
  let directory = $state<string | null>(untrack(() => projects.directory));
  let picking = $state(false);
  let error = $state<string | null>(null);
  let pending = $derived(projects.busy || picking);
  let folderName = $derived(directory?.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || directory || "Choose a folder…");

  async function chooseFolder(): Promise<void> {
    picking = true;
    error = null;
    try {
      const selected = await pickProjectDirectory(directory ?? undefined);
      if (selected !== null) directory = selected;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      picking = false;
    }
  }

  async function apply(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    if (pending) return;
    error = null;
    if (!name.trim() || name.trim() === "." || name.trim() === ".." || /^\.(pmmotor|pmsensor)$/i.test(name.trim()) || /[\\/:\x00-\x1f\x7f]/.test(name)) {
      error = "Enter a file name without slashes or colons.";
      return;
    }
    if (directory === null) await chooseFolder();
    if (directory === null) return;
    if (await projects.relocate(name, directory)) onClose();
    else error = projects.error;
  }

  function selectName(node: HTMLInputElement): void {
    node.focus();
    node.setSelectionRange(0, node.value.lastIndexOf(".") > 0 ? node.value.lastIndexOf(".") : node.value.length);
  }
</script>

<Dialog.Root bind:open onOpenChange={(value) => { if (!value && !pending) onClose(); }}>
  <Dialog.Portal>
    <Dialog.Overlay class="fixed inset-0 z-[140] bg-slate-950/80 backdrop-blur-sm" />
    <Dialog.Content
      onOpenAutoFocus={(event) => event.preventDefault()}
      onEscapeKeydown={(event) => { if (pending) event.preventDefault(); }}
      onInteractOutside={(event) => { if (pending) event.preventDefault(); }}
      class="fixed left-1/2 top-1/2 z-[141] w-[380px] max-w-[calc(100vw-1rem)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-slate-600 bg-slate-900 p-5 text-sm text-slate-100 shadow-2xl focus:outline-none"
    >
      <Dialog.Title class="text-base font-semibold">Rename file</Dialog.Title>
      <Dialog.Description class="mt-1 text-xs text-slate-400">Change the file name or move it to another folder.</Dialog.Description>
      <form onsubmit={apply} class="mt-4 space-y-3" aria-label="File name and location">
        <div class="grid grid-cols-[48px_minmax(0,1fr)] items-center gap-3">
          <label for="project-name" class="text-right text-xs text-slate-400">Name:</label>
          <input id="project-name" bind:value={name} {@attach selectName} disabled={pending} autocomplete="off" spellcheck="false" aria-invalid={error !== null} aria-describedby={error ? "project-location-error" : undefined} class="min-w-0 rounded-md border border-slate-600 bg-slate-950 px-2.5 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 disabled:opacity-50" />
          <span class="text-right text-xs text-slate-400">Where:</span>
          <button type="button" onclick={chooseFolder} disabled={pending} title={directory ?? "Choose a folder"} aria-label="Choose project folder" class="flex min-w-0 items-center gap-2 rounded-md border border-slate-600 bg-slate-800 px-2.5 py-2 text-left hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:opacity-50">
            <svg aria-hidden="true" width="16" height="16" viewBox="0 0 20 20" fill="none" class="shrink-0 text-sky-300"><path d="M2 6V4a1 1 0 0 1 1-1h5l2 2h7a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6Z" fill="currentColor" /></svg>
            <span class="truncate">{folderName}</span>
            <span aria-hidden="true" class="ml-auto text-slate-400">⌄</span>
          </button>
        </div>
        {#if error}<p id="project-location-error" role="alert" class="text-xs text-red-300">{error}</p>{/if}
        <div class="flex justify-end gap-2">
          <Dialog.Close type="button" disabled={pending} class="rounded-md px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500">Cancel</Dialog.Close>
          <button type="submit" disabled={pending} class="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 disabled:opacity-50">{pending ? "Working…" : projects.currentPath ? "Apply" : "Save"}</button>
        </div>
      </form>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
