import type { CadGeometry } from "../types";
import { simplifyCadLines } from "../cadSimplify";

interface Options {
  getGeometry: () => CadGeometry | null;
  onChange: (geometry: CadGeometry) => void;
}

/** Undo is available only until another edit replaces the simplified geometry. */
export class CadSimplifyTool {
  #options: Options;
  #before = $state.raw<CadGeometry | null>(null);
  #after = $state.raw<CadGeometry | null>(null);
  notice = $state("");
  constructor(options: Options) { this.#options = options; }
  get canUndo(): boolean { return this.#before !== null && this.#options.getGeometry() === this.#after; }
  simplify = () => {
    const geometry = this.#options.getGeometry();
    if (!geometry) return;
    const simplified = simplifyCadLines(geometry);
    const removed = geometry.routing.segments.length - simplified.routing.segments.length;
    this.notice = removed ? `${removed} line(s) merged.` : "No collinear lines to merge.";
    if (!removed) return;
    this.#before = geometry;
    this.#after = simplified;
    this.#options.onChange(simplified);
  };
  undo = () => {
    if (!this.canUndo || !this.#before) return;
    this.#options.onChange(this.#before);
    this.reset();
    this.notice = "Line simplification undone.";
  };
  reset = () => {
    this.#before = null;
    this.#after = null;
    this.notice = "";
  };
}
