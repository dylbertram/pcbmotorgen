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

<label class="grid min-w-0 content-start gap-1.5 text-xs text-slate-300">
  <span class="min-h-[2.5em] min-w-0 leading-relaxed">{label}</span>
  <NumberField
    {id}
    {value}
    {min}
    {max}
    {step}
    {integer}
    {disabled}
    ariaLabel={label}
    class="w-full min-w-0 px-2 py-1.5 text-xs font-mono text-emerald-200"
    {onCommit}
  />
</label>
