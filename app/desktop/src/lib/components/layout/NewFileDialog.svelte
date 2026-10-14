<script lang="ts">
  import { Dialog } from "bits-ui";
  import type { DocumentKind } from "../../types";
  let { busy, onCreate, onClose }: { busy: boolean; onCreate: (kind: DocumentKind) => void; onClose: () => void } = $props();
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
      <div class="mt-5 flex justify-end"><Dialog.Close disabled={busy} class="rounded px-3 py-2 text-sm text-slate-300 hover:bg-slate-800 focus-visible:outline focus-visible:outline-emerald-400">Cancel</Dialog.Close></div>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
