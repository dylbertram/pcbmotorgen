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
  get inferredPair() { return this.#base && this.active ? defaultCadTerminals(this.#base, this.coil) : null; }
  get candidates(): CadTerminal[] {
    if (!this.active || !this.#base) return [];
    const pair = this.inferredPair;
    return pair ? [pair.input, pair.output] : cadTerminalCandidates(this.#base, this.coil);
  }
  get layers(): number[] { return [...new Set(this.candidates.map((p) => p.layer))]; }
  get nextCoil(): string | undefined { const index = this.coils.indexOf(this.coil); return index >= 0 ? this.coils[index + 1] : undefined; }
  get canApply(): boolean { return this.active && this.step === "review" && this.input !== null && this.output !== null; }
  get connection(): "star" | "delta" { return this.#options.getGeometry()?.terminal_connection ?? "star"; }
  setConnection = (connection: "star" | "delta") => {
    const before = this.#options.getGeometry();
    if (!before || this.connection === connection) return;
    const active = this.active;
    const geometry = { ...before, terminal_connection: connection };
    this.#before = before;
    this.#after = geometry;
    this.#options.onChange(geometry);
    if (active) this.#base = geometry;
  };

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
    const candidates = cadTerminalCandidates(this.#base, coil);
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

  /** Retry inference into a draft. Saved/manual choices change only on Apply. */
  autoSelect = () => {
    if (!this.active) this.begin();
    if (!this.active || !this.#base || !this.coil) {
      this.error = "No trace endpoints available. Load or generate a winding first.";
      return;
    }
    const pair = defaultCadTerminals(this.#base, this.coil);
    if (!pair) {
      this.error = `Couldn't identify both ends for ${this.coil}. Select them manually.`;
      return;
    }
    this.input = pair.input;
    this.output = pair.output;
    this.defaultKind = "open";
    this.step = "review";
    this.error = "";
    this.notice = `Automatic ends found for ${this.coil}. Review them, then apply.`;
    this.#options.onReveal(this.coil, pair.input.layer);
    this.#options.onReveal(this.coil, pair.output.layer);
    this.#options.onFit?.();
  };

  change = (role: "input" | "output") => {
    if (!this.active || !this.coil) return;
    this.step = role;
    this.layer = this[role]?.layer ?? this.layers[0] ?? 0;
    this.error = "";
    this.#options.onReveal(this.coil, this.layer);
  };

  pick = (point: CadTerminal) => {
    if (!this.active || (this.step !== "input" && this.step !== "output") || !this.candidates.some((p) => sameTerminal(p, point))) return;
    const pair = this.inferredPair;
    if (pair && this.step === "input") {
      this.input = point;
      this.output = sameTerminal(point, pair.input) ? pair.output : pair.input;
      this.defaultKind = null;
      this.step = "review";
      this.error = "";
      this.#options.onReveal(this.coil, this.output.layer);
      return;
    }
    const other = this.step === "input" ? this.output : this.input;
    if (other && sameTerminal(other, point)) {
      this.error = "The driver end and opposite end must be different. Choose another endpoint.";
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

  /**
   * Re-anchor to a regenerated design (e.g. after a routing-parameter change)
   * and reselect its AUTOMATIC ends for the current coil. `CoilPreview`'s
   * generated terminal geometry is derived fresh on every parameter edit, so
   * without this the applied draft would silently stop updating.
   *
   * A geometry that keeps the same `routing` reference is one of this tool's
   * own edits (a connection-convention change), so the live draft is kept.
   */
  rebind = (geometry: CadGeometry | null): void => {
    if (this.step === null || !this.#base || !geometry) return;
    if (this.#base.routing === geometry.routing) return;
    const coil = this.coil;
    this.#base = geometry;
    this.begin(coil);
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
