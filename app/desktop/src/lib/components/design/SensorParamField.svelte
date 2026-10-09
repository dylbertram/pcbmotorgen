<script lang="ts">
  import NumberField from "../ui/NumberField.svelte";

  let {
    label,
    id,
    value,
    min,
    max,
    step,
    integer = false,
    disabled = false,
    onCommit,
  }: {
    label: string;
    id: string;
    value: number;
    min?: number;
    max?: number;
    step?: number;
    integer?: boolean;
    disabled?: boolean;
    onCommit: (value: number) => void;
  } = $props();
</script>

<label class="flex min-w-0 items-center justify-between gap-2 text-xs text-slate-300">
  <span class="min-w-0 truncate">{label}</span>
  <NumberField
    {id}
    {value}
    {min}
    {max}
    {step}
    {integer}
    {disabled}
    ariaLabel={label}
    class="w-24 shrink-0 px-2 py-1 text-xs font-mono text-emerald-200"
    {onCommit}
  />
</label>
