<script lang="ts">
  import { Popover } from "bits-ui";
  import { pickProjectDirectory } from "../../ipc/project";
  import type { ProjectStore } from "../../stores/project.svelte";

  let { projects }: { projects: ProjectStore } = $props();
  let open = $state(false);
  let name = $state("");
  let directory = $state<string | null>(null);
  let picking = $state(false);
  let error = $state<string | null>(null);
  let pending = $derived(projects.busy || picking);
  let folderName = $derived(directory?.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || directory || "Choose a folder…");

  function opened(value: boolean): void {
    if (!value) return;
    name = projects.fileName ?? projects.defaultFileName;
    directory = projects.directory;
    error = null;
  }

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
    if (await projects.relocate(name, directory)) open = false;
    else error = projects.error;
  }

  function selectName(node: HTMLInputElement): void {
    node.focus();
    node.setSelectionRange(0, node.value.lastIndexOf(".") > 0 ? node.value.lastIndexOf(".") : node.value.length);
  }
</script>

<Popover.Root bind:open onOpenChange={opened}>
  <Popover.Trigger
    disabled={projects.busy}
    aria-label="Change file name and location"
    title={projects.currentPath ?? "Change file name and location"}
    class="flex max-w-[280px] items-center gap-1.5 rounded px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:opacity-50"
  >
    <span class="truncate">{projects.label}</span>
    <svg aria-hidden="true" width="12" height="12" viewBox="0 0 12 12" fill="none" class="shrink-0"><path d="m3 4.5 3 3 3-3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" /></svg>
  </Popover.Trigger>
  <Popover.Portal>
    <Popover.Content
      side="bottom" align="center" sideOffset={10}
      onEscapeKeydown={(event) => { if (pending) event.preventDefault(); }}
      onInteractOutside={(event) => { if (pending) event.preventDefault(); }}
      class="z-[130] w-[360px] max-w-[calc(100vw-1rem)] rounded-xl border border-slate-600 bg-slate-900 p-4 text-sm text-slate-100 shadow-2xl"
    >
      <Popover.Arrow class="fill-slate-900" />
      <form onsubmit={apply} class="space-y-3" aria-label="File name and location">
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
          <Popover.Close disabled={pending} class="rounded-md px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500">Cancel</Popover.Close>
          <button type="submit" disabled={pending} class="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 disabled:opacity-50">{pending ? "Working…" : projects.currentPath ? "Apply" : "Save"}</button>
        </div>
      </form>
    </Popover.Content>
  </Popover.Portal>
</Popover.Root>
