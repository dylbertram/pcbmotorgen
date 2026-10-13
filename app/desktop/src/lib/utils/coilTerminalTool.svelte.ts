import type { CadGeometry, CadTerminal } from "../types";
import { assignCadTerminals, cadTerminalCandidates, sameTerminal } from "../cadTerminals";
import { cadCoilNames } from "../cadPreview";

interface Options {
  getGeometry: () => CadGeometry | null;
  onChange: (geometry: CadGeometry) => void;
  onReveal: (coil: string, layer: number) => void;
}

/** Draft-only command. The project changes once, when Done is pressed. */
export class CoilTerminalTool {
  step = $state<"coil" | "input" | "output" | "review" | null>(null);
  coil = $state("");
  layer = $state(0);
  input = $state.raw<CadTerminal | null>(null);
  output = $state.raw<CadTerminal | null>(null);
  notice = $state("");
  error = $state("");
  #base: CadGeometry | null = null;
  #options: Options;
  constructor(options: Options) { this.#options = options; }

  get active(): boolean { return this.step !== null && this.#base === this.#options.getGeometry(); }
  get coils(): string[] { const g = this.#options.getGeometry(); return g ? cadCoilNames(g).filter((coil) => cadTerminalCandidates(g, coil).length >= 2) : []; }
  get candidates(): CadTerminal[] { return this.active && this.#base ? cadTerminalCandidates(this.#base, this.coil) : []; }
  get layers(): number[] { return [...new Set(this.candidates.map((p) => p.layer))]; }

  begin = () => {
    this.#base = this.#options.getGeometry();
    if (!this.#base) return;
    this.step = "coil";
    this.coil = "";
    this.input = null;
    this.output = null;
    this.error = "";
    this.notice = "";
  };
  chooseCoil = (coil: string) => {
    if (!this.active || !this.coils.includes(coil)) return;
    this.coil = coil;
    this.input = null;
    this.output = null;
    this.step = "coil";
    this.layer = this.layers[0] ?? 0;
    this.error = "";
    this.#options.onReveal(coil, this.layer);
  };
  chooseLayer = (layer: number) => {
    if (!this.active || !this.layers.includes(layer)) return;
    this.layer = layer;
    this.#options.onReveal(this.coil, layer);
  };
  next = () => { if (this.active && this.step === "coil" && this.coil) this.step = "input"; };
  pick = (point: CadTerminal) => {
    if (!this.active || point.layer !== this.layer || !this.candidates.some((p) => sameTerminal(p, point))) return;
    if (this.step === "input") {
      this.input = point;
      this.output = null;
      this.step = "output";
    } else if (this.step === "output") {
      if (this.input && sameTerminal(this.input, point)) {
        this.error = "OUT must be different from IN. Choose another endpoint.";
        return;
      }
      this.output = point;
      this.step = "review";
    }
    this.error = "";
  };
  back = () => {
    if (!this.active) return;
    if (this.step === "review") { this.output = null; this.step = "output"; }
    else if (this.step === "output") { this.input = null; this.output = null; this.step = "input"; }
    else { this.input = null; this.output = null; this.step = "coil"; }
    this.error = "";
  };
  cancel = () => {
    this.step = null;
    this.input = null;
    this.output = null;
    this.error = "";
    this.#base = null;
  };
  done = () => {
    if (!this.active || this.step !== "review" || !this.#base || !this.input || !this.output) return;
    const geometry = assignCadTerminals(this.#base, this.coil, { input: this.input, output: this.output });
    this.notice = `Coil ${this.coil} IN and OUT set. Save the project to keep them.`;
    this.cancel();
    this.#options.onChange(geometry);
  };
}
