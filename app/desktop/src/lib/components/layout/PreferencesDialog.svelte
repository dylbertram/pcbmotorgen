<script lang="ts">
  import { Dialog } from "bits-ui";
  import { untrack } from "svelte";
  import type { ConfigStore } from "../../stores/config.svelte";
  import { DEFAULT_RULES, RULE_FIELDS, readPreferences, writePreferences, validRules, type Appearance, type DrcRules } from "../../preferences";
  import { attachBackdropScrollGuard, lockPageScroll } from "../../utils/pageScrollLock";

  let { config, disabled = false, onClose }: { config: ConfigStore; disabled?: boolean; onClose: () => void } = $props();
  let open = $state(true);
  let appearance = $state<Appearance>(untrack(() => readPreferences().appearance));
  let rules = $state<DrcRules>(untrack(() => ({
    min_trace_mm: config.min_trace_mm,
    min_space_mm: config.min_space_mm,
    min_via_drill_mm: config.min_via_drill_mm,
    min_via_annular_ring_mm: config.min_via_annular_ring_mm,
  })));
  let error = $state<string | null>(null);
  let valid = $derived(validRules(rules));
  let backdropRef = $state<HTMLDivElement | null>(null);
  let panelRef = $state<HTMLDivElement | null>(null);
  const appearances = [{ value: "light", label: "Light" }, { value: "dark", label: "Dark" }, { value: "auto", label: "Auto" }] as const;

  $effect(() => {
    if (!backdropRef) return;
    const detach = attachBackdropScrollGuard(backdropRef, panelRef);
    const unlock = lockPageScroll(document);
    return () => { detach(); unlock(); };
  });

  function save(event: SubmitEvent): void {
    event.preventDefault();
    if (!valid || disabled) return;
    try {
      writePreferences({ appearance, rules: { ...rules } });
      Object.assign(config, rules);
      onClose();
    } catch (reason) {
      error = `Could not save settings. ${reason instanceof Error ? reason.message : String(reason)}`;
    }
  }
</script>

<Dialog.Root bind:open onOpenChange={(value) => { if (!value) onClose(); }}>
  <Dialog.Portal>
    <Dialog.Overlay bind:ref={backdropRef} class="fixed inset-0 z-[140] bg-slate-950/80 backdrop-blur-sm" />
    <Dialog.Content bind:ref={panelRef} preventScroll={false} class="fixed left-1/2 top-1/2 z-[141] max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto overscroll-contain rounded-xl border border-slate-700 bg-slate-900 text-slate-100 shadow-2xl focus:outline-none">
      <form onsubmit={save} class="flex max-h-[calc(100dvh-2rem)] flex-col">
        <header class="shrink-0 border-b border-slate-700 px-5 py-4">
          <Dialog.Title class="text-base font-semibold">Settings</Dialog.Title>
          <Dialog.Description class="mt-1 text-xs text-slate-400">Appearance and design rule defaults for this app.</Dialog.Description>
        </header>
        <div class="min-h-0 overflow-y-auto overscroll-contain space-y-6 px-5 py-5">
          <fieldset>
            <legend class="mb-3 text-sm font-semibold">Appearance</legend>
            <div class="grid grid-cols-3 gap-2">
              {#each appearances as mode (mode.value)}
                <label class="relative cursor-pointer rounded-md border px-3 py-3 text-center text-sm has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-emerald-500 {appearance === mode.value ? 'border-emerald-500 bg-emerald-500/10 text-emerald-300' : 'border-slate-700 text-slate-300 hover:bg-slate-800'}">
                  <input class="absolute inset-0 h-full w-full cursor-pointer opacity-0" type="radio" name="appearance" value={mode.value} bind:group={appearance} />
                  {mode.label}
                </label>
              {/each}
            </div>
            <p class="mt-2 text-xs text-slate-400">Auto follows your system's light or dark appearance.</p>
          </fieldset>

          <fieldset disabled={disabled}>
            <legend class="text-sm font-semibold">DRC rules</legend>
            <p class="mb-4 mt-2 text-xs leading-relaxed text-slate-400">Applied to the current motor design and saved as defaults for new designs. Opened projects keep their saved rules. These values also control routing and via sizing.</p>
            <div class="space-y-3">
              {#each RULE_FIELDS as field (field.key)}
                <div class="flex items-center justify-between gap-3">
                  <label for="settings-{field.key}" class="text-xs text-slate-300">{field.label} <span class="text-slate-400">(mm)</span></label>
                  <input id="settings-{field.key}" type="number" min="0.001" step="any" required bind:value={rules[field.key]} class="w-28 shrink-0 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-right text-sm tabular-nums focus:border-emerald-500 focus:outline-none disabled:opacity-50" />
                </div>
              {/each}
            </div>
            <button type="button" onclick={() => { rules = { ...DEFAULT_RULES }; }} class="mt-4 text-xs text-slate-400 underline decoration-slate-600 underline-offset-4 hover:text-slate-200">Restore default rules</button>
            {#if !valid}<p class="mt-3 text-xs text-rose-300" role="alert">Enter a positive number for every rule.</p>{/if}
          </fieldset>
          {#if error}<p role="alert" class="text-xs text-rose-300">{error}</p>{/if}
        </div>
        <footer class="flex shrink-0 justify-end gap-2 border-t border-slate-700 px-5 py-3">
          <Dialog.Close class="rounded-md border border-slate-700 px-4 py-2 text-xs text-slate-300 hover:bg-slate-800">Cancel</Dialog.Close>
          <button type="submit" disabled={!valid || disabled} class="rounded-md border border-emerald-500/40 bg-emerald-600/20 px-4 py-2 text-xs font-medium text-emerald-300 hover:bg-emerald-600/30 disabled:opacity-50">Save settings</button>
        </footer>
      </form>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
