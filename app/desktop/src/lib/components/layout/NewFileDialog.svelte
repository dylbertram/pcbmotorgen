<script lang="ts">
  import { onMount } from "svelte";
  import { Dialog } from "bits-ui";
  import { listCoilFiles } from "../../ipc";
  import type { DocumentKind } from "../../types";

  let {
    busy,
    directories = [],
    openPaths = [],
    onCreate,
    onOpenFile,
    onClose,
  }: {
    busy: boolean;
    directories?: string[];
    openPaths?: string[];
    onCreate: (kind: DocumentKind) => void;
    onOpenFile?: (path: string) => void;
    onClose: () => void;
  } = $props();

  interface ListedCoilFile {
    path: string;
    displayPath: string;
    kind: DocumentKind;
  }

  let loadingFiles = $state(false);
  let folderFiles = $state.raw<ListedCoilFile[]>([]);

  function formatDisplayPath(path: string, roots: string[]): string {
    const normalized = path.replace(/\\/g, "/");
    for (const root of roots) {
      const prefix = root.replace(/\\/g, "/").replace(/\/+$/, "") + "/";
      if (normalized.startsWith(prefix)) {
        return normalized.slice(prefix.length);
      }
    }
    return normalized.split("/").pop() ?? path;
  }

  onMount(() => {
    if (directories.length === 0) return;
    loadingFiles = true;
    const openSet = new Set(openPaths);
    void Promise.all(directories.map((dir) => listCoilFiles(dir).catch(() => [])))
      .then((lists) => {
        const seen = new Set<string>();
        const items: ListedCoilFile[] = [];
        for (const list of lists) {
          for (const path of list) {
            if (openSet.has(path) || seen.has(path)) continue;
            const kind: DocumentKind | null = /\.pmsensor$/i.test(path)
              ? "sensor"
              : /\.pmmotor$/i.test(path)
                ? "motor"
                : null;
            if (!kind) continue;
            seen.add(path);
            items.push({
              path,
              displayPath: formatDisplayPath(path, directories),
              kind,
            });
          }
        }
        folderFiles = items;
      })
      .finally(() => {
        loadingFiles = false;
      });
  });
</script>

<Dialog.Root open onOpenChange={(open) => { if (!open && !busy) onClose(); }}>
  <Dialog.Portal>
    <Dialog.Overlay class="fixed inset-0 z-[140] bg-slate-950/80 backdrop-blur-sm" />
    <Dialog.Content onInteractOutside={(event) => { if (busy) event.preventDefault(); }} onEscapeKeydown={(event) => { if (busy) event.preventDefault(); }} class="fixed left-1/2 top-1/2 z-[141] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-xl border border-slate-600 bg-slate-900 p-6 text-slate-100 shadow-2xl focus:outline-none">
      <Dialog.Title class="text-lg font-semibold">New coil file</Dialog.Title>
      <Dialog.Description class="mt-1 text-sm text-slate-400">Choose a coil type. The new file opens in its own tab.</Dialog.Description>
      <div class="mt-5 grid gap-3 sm:grid-cols-2">
        <button type="button" disabled={busy} onclick={() => onCreate("motor")} class="rounded-lg border border-slate-600 bg-slate-800 p-4 text-left hover:border-emerald-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400 disabled:opacity-50">
          <span class="block font-medium">Motor coil</span>
          <span class="mt-1 block text-xs text-slate-400">Motor winding, motion and simulation</span>
          <span class="mt-3 block font-mono text-xs text-emerald-300">.pmmotor</span>
        </button>
        <button type="button" disabled={busy} onclick={() => onCreate("sensor")} class="rounded-lg border border-slate-600 bg-slate-800 p-4 text-left hover:border-sky-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400 disabled:opacity-50">
          <span class="block font-medium">Sensor coil</span>
          <span class="mt-1 block text-xs text-slate-400">Inductive position sensor</span>
          <span class="mt-3 block font-mono text-xs text-sky-300">.pmsensor</span>
        </button>
      </div>
      {#if loadingFiles || folderFiles.length > 0 || directories.length > 0}
        <div class="mt-5 border-t border-slate-800 pt-4">
          <h3 class="text-xs font-semibold uppercase tracking-wider text-slate-400">Other files in folder</h3>
          {#if loadingFiles}
            <p class="mt-2 text-xs text-slate-500">Scanning folder…</p>
          {:else if folderFiles.length === 0}
            <p class="mt-2 text-xs text-slate-500">No other .pmmotor or .pmsensor files in this folder.</p>
          {:else}
            <ul class="mt-2 max-h-48 divide-y divide-slate-800 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950/50" aria-label="Other coil files in folder">
              {#each folderFiles as file (file.path)}
                <li>
                  <button
                    type="button"
                    disabled={busy}
                    onclick={() => onOpenFile?.(file.path)}
                    class="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-xs hover:bg-slate-800 focus-visible:outline focus-visible:outline-emerald-400 disabled:opacity-50"
                  >
                    <span class="flex min-w-0 items-center gap-2">
                      <span class="font-mono font-semibold {file.kind === 'motor' ? 'text-emerald-300' : 'text-sky-300'}">{file.kind === "motor" ? "M" : "S"}</span>
                      <span class="truncate text-slate-200">{file.displayPath}</span>
                    </span>
                    <span class="shrink-0 font-mono text-[11px] text-slate-500">.{file.kind === "motor" ? "pmmotor" : "pmsensor"}</span>
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      {/if}
      <div class="mt-5 flex justify-end"><Dialog.Close disabled={busy} class="rounded px-3 py-2 text-sm text-slate-300 hover:bg-slate-800 focus-visible:outline focus-visible:outline-emerald-400">Cancel</Dialog.Close></div>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
