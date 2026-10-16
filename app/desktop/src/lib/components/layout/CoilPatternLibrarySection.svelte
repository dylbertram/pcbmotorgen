<script lang="ts">
  import type { ConfigStore } from "../../stores/config.svelte";
  import type { InstalledPlugin } from "../../types";
  import { listInstalledPlugins, removeRoutingPlugin } from "../../ipc";

  let { config, disabled = false }: { config: ConfigStore; disabled?: boolean } = $props();

  let installed = $state<InstalledPlugin[]>([]);
  let loading = $state(true);
  let busyId = $state<string | null>(null);
  let error = $state<string | null>(null);
  let notice = $state<string | null>(null);

  async function refresh(): Promise<void> {
    loading = true;
    try {
      installed = await listInstalledPlugins();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  $effect(() => { void refresh(); });

  const installedIds = $derived(new Set(installed.map((plugin) => plugin.id)));
  const builtIn = $derived(config.routing_patterns.filter((pattern) => !installedIds.has(pattern.id)));

  async function remove(plugin: InstalledPlugin): Promise<void> {
    busyId = plugin.id;
    error = null;
    notice = null;
    try {
      await removeRoutingPlugin(plugin.id);
      // The catalog the Design tab selects from must drop the pattern too.
      await config.loadRoutingPatterns();
      if (config.routing_pattern === plugin.id && config.routing_patterns.length > 0) {
        config.routing_pattern = config.routing_patterns[0].id;
        await config.loadRoutingParams(config.routing_pattern);
      }
      notice = `Removed ${plugin.display_name || plugin.id}.`;
      await refresh();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busyId = null;
    }
  }
</script>

<fieldset disabled={disabled}>
  <legend class="text-sm font-semibold">Coil pattern library</legend>
  <p class="mb-3 mt-2 text-xs leading-relaxed text-slate-400">
    The routing generators the Design tab can select. Load new ones from Design &rsaquo; Routing source; remove them here.
  </p>

  {#if loading}
    <p role="status" class="text-xs text-slate-500">Reading the pattern library…</p>
  {:else}
    <p class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Bundled</p>
    <ul class="mb-4 space-y-1">
      {#each builtIn as pattern (pattern.id)}
        <li class="flex items-center justify-between gap-3 rounded-md border border-slate-700 bg-slate-800/40 px-3 py-2">
          <span class="min-w-0 truncate text-xs text-slate-200" title={pattern.id}>{pattern.display_name}</span>
          <span class="shrink-0 text-[10px] uppercase tracking-wide text-slate-500">Built-in</span>
        </li>
      {/each}
      {#if builtIn.length === 0}<li class="text-xs text-slate-500">No bundled patterns available.</li>{/if}
    </ul>

    <p class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Installed</p>
    <ul class="space-y-1">
      {#each installed as plugin (plugin.id)}
        <li class="flex items-start justify-between gap-3 rounded-md border border-slate-700 bg-slate-800/40 px-3 py-2">
          <div class="min-w-0">
            <p class="truncate text-xs text-slate-200" title={plugin.id}>{plugin.display_name || plugin.id}</p>
            <p class="mt-0.5 text-[11px] text-slate-500">
              {plugin.kind}{plugin.author ? ` · ${plugin.author}` : ""}{plugin.version ? ` · v${plugin.version}` : ""}
            </p>
          </div>
          <button
            type="button"
            aria-label={`Remove ${plugin.display_name || plugin.id}`}
            disabled={busyId !== null}
            onclick={() => remove(plugin)}
            class="shrink-0 rounded border border-rose-500/50 px-2 py-1 text-xs text-rose-200 hover:bg-rose-500/10 disabled:opacity-50"
          >
            {busyId === plugin.id ? "Removing…" : "Remove"}
          </button>
        </li>
      {/each}
      {#if installed.length === 0}<li class="text-xs text-slate-500">No user-installed generators.</li>{/if}
    </ul>
  {/if}

  {#if notice}<p role="status" class="mt-2 text-xs text-emerald-300">{notice}</p>{/if}
  {#if error}<p role="alert" class="mt-2 text-xs text-rose-300">{error}</p>{/if}
</fieldset>
