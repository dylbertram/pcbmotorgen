<script lang="ts">
  import { ContextMenu } from "bits-ui";
  import type { DocumentSession } from "../../stores/workspace.svelte";
  import type { EditorSide } from "../../stores/editorGroups.svelte";
  let { documents, selected, side, busy, onSelect, onClose, onVersions, onRename, onReveal, onNew, onSplit, onDrag, onDragEnd }: {
    documents: DocumentSession[]; selected: number | null; side: EditorSide; busy: boolean;
    onSelect: (id: number) => void; onClose: (id: number) => void;
    onVersions: (document: DocumentSession, creating: boolean) => void;
    onRename: (document: DocumentSession) => void; onReveal: (document: DocumentSession) => void;
    onNew: () => void; onSplit: (id: number) => void;
    onDrag: (id: number, side: EditorSide) => void; onDragEnd: () => void;
  } = $props();
  const item = "cursor-pointer rounded px-3 py-2 text-xs outline-none data-[highlighted]:bg-slate-700 data-[disabled]:opacity-40";
  async function keydown(event: KeyboardEvent, index: number): Promise<void> {
    const next = event.key === "ArrowRight" ? (index + 1) % documents.length
      : event.key === "ArrowLeft" ? (index + documents.length - 1) % documents.length
      : event.key === "Home" ? 0 : event.key === "End" ? documents.length - 1 : null;
    if (next === null || busy) return;
    event.preventDefault();
    onSelect(documents[next].id);
    document.getElementById(`file-tab-${side}-${documents[next].id}`)?.focus();
  }
</script>

<nav class="flex min-h-10 min-w-0 shrink-0 items-stretch overflow-x-auto border-b border-slate-700 bg-slate-950/60 {side === 'left' ? 'pl-[95px]' : ''}" aria-label={side === "left" ? "Open files" : "Right editor files"} data-tauri-drag-region>
  <div role="tablist" aria-label={side === "left" ? "Coil files" : "Right coil files"} class="flex items-stretch">
    {#each documents as source, index (source.id)}
      <ContextMenu.Root>
        <ContextMenu.Trigger class="flex shrink-0 items-center gap-1 border-r border-t-2 border-slate-700 pr-1 {selected === source.id ? 'border-t-emerald-400 bg-slate-800' : 'border-t-transparent bg-slate-950/30'}">
          <button type="button" role="tab" id={`file-tab-${side}-${source.id}`} aria-controls={`document-${side}-${source.id}`} aria-selected={selected === source.id} tabindex={selected === source.id ? 0 : -1}
            draggable={!busy} ondragstart={(event) => { event.dataTransfer?.setData("application/x-pcbmotorgen-tab", String(source.id)); if (event.dataTransfer) event.dataTransfer.effectAllowed = "move"; onDrag(source.id, side); }} ondragend={onDragEnd}
            onkeydown={(event) => void keydown(event, index)} class="flex items-center gap-2 px-3 py-2 text-xs focus-visible:outline focus-visible:outline-emerald-400 disabled:opacity-50" disabled={busy}
            title={source.projects.currentPath ?? source.projects.defaultFileName} onclick={() => onSelect(source.id)}>
            <span class={source.kind === "motor" ? "text-emerald-300" : "text-sky-300"}>{source.kind === "motor" ? "M" : "S"}</span>
            <span>{source.title}</span>
            {#if source.projects.isDirty || source.projects.currentPath === null}<span class="text-amber-300" aria-label={source.projects.isDirty ? "Unsaved changes" : "Unsaved file"}>●</span>{/if}
          </button>
          <button type="button" onclick={() => onVersions(source, false)} disabled={busy}
            aria-label={selected === source.id ? "Project versions" : `Project versions for ${source.title}`}
            class="shrink-0 rounded border border-slate-700 bg-slate-900/70 px-1.5 py-0.5 text-[10px] text-slate-300 hover:border-emerald-500/50 hover:text-emerald-200 focus-visible:outline focus-visible:outline-emerald-400">
            {source.projects.activeVersionId !== null ? `Version ${source.projects.activeVersionId}` : "Versions"}
          </button>
          <button type="button" class="rounded px-1.5 py-0.5 text-slate-500 hover:bg-slate-700 hover:text-slate-100 focus-visible:outline focus-visible:outline-emerald-400" disabled={busy} aria-label={`Close ${source.title}`} onclick={() => onClose(source.id)}>×</button>
        </ContextMenu.Trigger>
        <ContextMenu.Portal>
          <ContextMenu.Content preventScroll={false} class="z-[150] min-w-44 rounded-lg border border-slate-600 bg-slate-800 p-1 text-slate-100 shadow-xl">
            <ContextMenu.Item class={item} disabled={busy} onSelect={() => onSplit(source.id)}>Split right</ContextMenu.Item>
            <ContextMenu.Separator class="my-1 h-px bg-slate-600" />
            <ContextMenu.Item class={item} disabled={busy} onSelect={() => onRename(source)}>Rename</ContextMenu.Item>
            <ContextMenu.Item class={item} disabled={busy || !source.projects.currentPath} onSelect={() => onReveal(source)}>Reveal in Finder</ContextMenu.Item>
            <ContextMenu.Item class={item} disabled={busy} onSelect={() => { void source.projects.save(false); }}>Save</ContextMenu.Item>
            <ContextMenu.Item class={item} disabled={busy} onSelect={() => onVersions(source, true)}>Save new version</ContextMenu.Item>
            <ContextMenu.Separator class="my-1 h-px bg-slate-600" />
            <ContextMenu.Item class={item} disabled={busy} onSelect={() => onClose(source.id)}>Close</ContextMenu.Item>
          </ContextMenu.Content>
        </ContextMenu.Portal>
      </ContextMenu.Root>
    {/each}
  </div>
  <button type="button" class="shrink-0 px-4 py-2 text-slate-400 hover:bg-slate-800 focus-visible:outline focus-visible:outline-emerald-400" disabled={busy} aria-label="New coil file" onclick={onNew}>+</button>
</nav>
