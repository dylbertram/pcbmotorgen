import type { CadGeometry, CadPoint } from "../types";
import { reassignTraces, traceChain, traceDistance, traceInBox, type SelectionBox, type SelectableTrace } from "../cadSelection";

export class CadSelectionTool {
  mode = $state<"pan" | "select" | "chain" | "box">("pan");
  selected = $state<string[]>([]);
  crossing = $state(true);
  boxAction = $state<"replace" | "add" | "remove">("replace");
  anchor = $state<string | null>(null);
  notice = $state("");
  before = $state.raw<CadGeometry | null>(null);
  after = $state.raw<CadGeometry | null>(null);
  constructor(private options: { getGeometry: () => CadGeometry | null; onChange: (geometry: CadGeometry) => void; tolerance?: () => number }) {}
  clear = () => { this.selected = []; this.anchor = null; this.notice = ""; };
  setMode = (mode: typeof this.mode) => { this.mode = mode; this.anchor = null; this.notice = ""; };
  pick(point: CadPoint, traces: SelectableTrace[], tolerance: number, shift: boolean) {
    const hit = traces.map((trace) => ({ trace, distance: traceDistance(point, trace) })).filter((hit) => hit.distance <= tolerance).sort((a, b) => a.distance - b.distance)[0]?.trace;
    if (!hit) { if (!shift) this.clear(); return; }
    this.pickTrace(hit.id, traces, shift);
  }
  pickTrace(id: string, traces: SelectableTrace[], shift: boolean) {
    const hit = traces.find((trace) => trace.id === id);
    if (!hit) return;
    if (this.mode === "chain") {
      if (!this.anchor) { this.anchor = hit.id; this.selected = shift ? [...new Set([...this.selected, hit.id])] : [hit.id]; this.notice = "Choose the last segment."; return; }
      const chain = traceChain(traces, this.anchor, hit.id, this.options.tolerance?.() ?? 0.05, this.options.getGeometry()?.routing.vias);
      if (!chain.length) { this.notice = "No connected chain. Choose another segment."; return; }
      this.selected = shift ? [...new Set([...this.selected, ...chain])] : chain;
      this.anchor = null;
      this.notice = "Chain selected.";
    } else this.selected = shift ? this.selected.includes(hit.id) ? this.selected.filter((id) => id !== hit.id) : [...this.selected, hit.id] : [hit.id];
  }
  selectBox(box: SelectionBox, traces: SelectableTrace[], shift: boolean) {
    const hits = traces.filter((trace) => traceInBox(trace, box, this.crossing)).map((t) => t.id);
    const action = shift && this.boxAction === "replace" ? "add" : this.boxAction;
    const hitIds = new Set(hits);
    this.selected = action === "replace" ? hits : action === "add" ? [...new Set([...this.selected, ...hits])] : this.selected.filter((id) => !hitIds.has(id));
  }
  apply(net: string, layer: string) {
    const geometry = this.options.getGeometry();
    if (!geometry || !this.selected.length || (!net.trim() && layer === "")) return;
    const layerIndex = layer === "" ? undefined : Number(layer);
    if (layerIndex !== undefined && (!Number.isInteger(layerIndex) || layerIndex < 0 || layerIndex >= geometry.layer_z_mm.length)) return;
    this.before = geometry;
    this.after = reassignTraces(geometry, this.selected, net.trim() || undefined, layerIndex);
    this.options.onChange(this.after);
    this.notice = "Assignment updated. Check coil terminals before export.";
  }
  undo = () => {
    if (!this.before || this.options.getGeometry() !== this.after) return;
    this.options.onChange(this.before);
    this.before = null; this.after = null;
    this.notice = "Assignment undone.";
  };
  get canUndo() { return this.before !== null && this.options.getGeometry() === this.after; }
}
