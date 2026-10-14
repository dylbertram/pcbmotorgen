import type { CadGeometry, CadTerminal } from "../types";
import { assignCadTerminals, cadTerminalCandidates, defaultCadTerminals, sameTerminal } from "../cadTerminals";
import { cadCoilNames } from "../cadPreview";

interface Options {
  getGeometry: () => CadGeometry | null;
  onChange: (geometry: CadGeometry) => void;
  onReveal: (coil: string, layer: number) => void;
  onFit?: () => void;
}

/** Endpoint choices stay draft-only until applied. */
export class CoilTerminalTool {
  step = $state<"coil" | "input" | "output" | "review" | null>(null);
  coil = $state("");
  layer = $state(0);
  input = $state.raw<CadTerminal | null>(null);
  output = $state.raw<CadTerminal | null>(null);
  defaultKind = $state<"open" | "saved" | null>(null);
  notice = $state("");
  error = $state("");
  #base: CadGeometry | null = null;
  #before = $state.raw<CadGeometry | null>(null);
  #after = $state.raw<CadGeometry | null>(null);
  #options: Options;
  constructor(options: Options) { this.#options = options; }

  get active(): boolean { return this.step !== null && this.#base === this.#options.getGeometry(); }
  /** Undo is available only until another edit replaces the applied geometry. */
  get canUndo(): boolean { return this.#before !== null && this.#options.getGeometry() === this.#after; }
  undo = () => {
    if (!this.canUndo || !this.#before) return;
    this.#options.onChange(this.#before);
    this.#before = null; this.#after = null;
    this.notice = "Terminal change undone.";
  };
  get coils(): string[] { const g = this.#options.getGeometry(); return g ? cadCoilNames(g).filter((coil) => cadTerminalCandidates(g, coil).length >= 2) : []; }
  get candidates(): CadTerminal[] { return this.active && this.#base ? cadTerminalCandidates(this.#base, this.coil) : []; }
  get layers(): number[] { return [...new Set(this.candidates.map((p) => p.layer))]; }
  get nextCoil(): string | undefined { const index = this.coils.indexOf(this.coil); return index >= 0 ? this.coils[index + 1] : undefined; }
  get canApply(): boolean { return this.active && this.step === "review" && this.input !== null && this.output !== null; }

  begin = (coil?: string) => {
    this.#base = this.#options.getGeometry();
    if (!this.#base) return;
    this.step = "coil";
    this.coil = "";
    this.input = null;
    this.output = null;
    this.defaultKind = null;
    this.error = "";
    this.notice = "";
    const selected = coil && this.coils.includes(coil) ? coil : this.coils[0];
    if (selected) this.chooseCoil(selected);
  };

  chooseCoil = (coil: string) => {
    if (!this.active || !this.#base || !this.coils.includes(coil)) return;
    this.coil = coil;
    const saved = Object.hasOwn(this.#base.coil_terminals ?? {}, coil) ? this.#base.coil_terminals![coil] : undefined;
    const candidates = this.candidates;
    const savedValid = saved && !sameTerminal(saved.input, saved.output)
      && [saved.input, saved.output].every((point) => candidates.some((candidate) => sameTerminal(candidate, point)));
    const defaults = savedValid ? saved : defaultCadTerminals(this.#base, coil);
    this.input = defaults?.input ?? null;
    this.output = defaults?.output ?? null;
    this.defaultKind = defaults ? savedValid ? "saved" : "open" : null;
    this.step = defaults ? "review" : "input";
    this.layer = this.input?.layer ?? this.layers[0] ?? 0;
    this.error = "";
    this.#options.onReveal(coil, this.layer);
    if (this.output && this.output.layer !== this.layer) this.#options.onReveal(coil, this.output.layer);
    this.#options.onFit?.();
  };

  chooseLayer = (layer: number) => {
    if (!this.active || !this.layers.includes(layer)) return;
    this.layer = layer;
    this.#options.onReveal(this.coil, layer);
  };

  change = (role: "input" | "output") => {
    if (!this.active || !this.coil) return;
    this.step = role;
    this.layer = this[role]?.layer ?? this.layers[0] ?? 0;
    this.error = "";
    this.#options.onReveal(this.coil, this.layer);
  };

  pick = (point: CadTerminal) => {
    if (!this.active || (this.step !== "input" && this.step !== "output") || point.layer !== this.layer || !this.candidates.some((p) => sameTerminal(p, point))) return;
    const other = this.step === "input" ? this.output : this.input;
    if (other && sameTerminal(other, point)) {
      this.error = "IN and OUT must be different. Choose another endpoint.";
      return;
    }
    this[this.step] = point;
    this.defaultKind = null;
    this.step = this.input && this.output ? "review" : this.input ? "output" : "input";
    this.error = "";
  };

  finishPicking = () => {
    if (!this.active || !this.input || !this.output) return;
    this.step = "review";
    this.error = "";
  };

  flip = () => {
    if (!this.active || !this.input || !this.output) return;
    [this.input, this.output] = [this.output, this.input];
    this.defaultKind = null;
    this.step = "review";
    this.error = "";
  };

  cancel = () => {
    this.step = null;
    this.input = null;
    this.output = null;
    this.defaultKind = null;
    this.error = "";
    this.#base = null;
  };

  #apply(next: boolean) {
    if (!this.canApply || !this.#base || !this.input || !this.output) return;
    const nextCoil = next ? this.nextCoil : undefined;
    const before = this.#base;
    const geometry = assignCadTerminals(this.#base, this.coil, { input: this.input, output: this.output });
    this.#before = before;
    this.#after = geometry;
    this.notice = `Coil ${this.coil} terminals updated. Save the project to keep them.`;
    this.cancel();
    this.#options.onChange(geometry);
    if (nextCoil) { this.begin(nextCoil); this.notice = "Previous coil updated."; }
  }
  done = () => this.#apply(false);
  applyAndNext = () => this.#apply(true);
}
