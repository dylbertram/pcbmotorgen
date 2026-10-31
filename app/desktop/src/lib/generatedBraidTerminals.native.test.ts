import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { generatedTerminalGeometry } from "./generatedTerminalGeometry";
import { cadTerminalCandidates, sameTerminal, withAutomaticCadTerminals } from "./cadTerminals";
import type { CoilPathDto } from "./types";
import { CoilTerminalTool } from "./utils/coilTerminalTool.svelte";
import { buildCoilScene } from "./coilScene";

// Exported by the real generate_coils command in the supplied-reference test.
// Keep the user's project/DXF inputs out of the repository and test directly
// against a fresh native payload when running this cross-language regression.
const fixtureDirectory = process.env.PCB_MOTOR_TERMINAL_FIXTURES;
describe.skipIf(!fixtureDirectory)("native generated braid terminal handoff", () => {
  const cases = [3, 5].flatMap((strands) => [2, 4, 6, 8].map((layers) => ({ strands, layers })));
  for (const { strands, layers } of cases) {
    it(`selects driver ends and shared neutral through the ${layers}-layer ${strands}-strand IPC payload`, () => {
      const filename = strands === 3 ? `generated-${layers}-preview.json` : `generated-${layers}-five-strand-preview.json`;
      const coils = JSON.parse(readFileSync(join(fixtureDirectory!, filename), "utf8")) as CoilPathDto;
      const before = JSON.stringify(coils);
      const geometry = generatedTerminalGeometry(coils, layers, 1.6, .2, 2);
      const scene = buildCoilScene(geometry)!;
      const fullStackVias = scene.vias.filter(via => Math.abs(via.to_layer - via.from_layer) === layers - 1);
      expect(fullStackVias.length).toBeGreaterThan(0);
      for (const via of fullStackVias) {
        expect(Math.abs(via.points[0].y - via.points[1].y) / scene.scale).toBeCloseTo(1.6, 12);
      }
      const revealed: [string, number][] = [];
      const tool = new CoilTerminalTool({ getGeometry: () => geometry, onChange: () => {},
        onReveal: (net, layer) => revealed.push([net, layer]) });
      for (const [i, net] of ["A", "B", "C"].entries()) {
        const pair = geometry.coil_terminals?.[net];
        expect(pair, `${net} must have automatically selected ends`).toBeDefined();
        expect(pair!.input.layer).toBe(layers - 1);
        expect(pair!.input.position.x).toBeCloseTo(0, 9);
        expect(pair!.input.position.y).toBeCloseTo(8 + (i + 1) * 4 / (3 * strands), 9);
        expect(pair!.output.layer).toBe(0);
        expect(pair!.output.position.x).toBeCloseTo(5 + (strands - 1) * 6 / (3 * strands) + 6 * (layers / 2 - 1), 9);
        expect(pair!.output.position.y).toBeCloseTo(8 + 4 / (3 * strands), 9);
        const candidates = cadTerminalCandidates(geometry, net);
        expect(candidates.some((p) => sameTerminal(p, pair!.input))).toBe(true);
        expect(candidates.some((p) => sameTerminal(p, pair!.output))).toBe(true);
        revealed.length = 0;
        tool.begin(net);
        expect(tool.step).toBe("review");
        expect(tool.canApply).toBe(true);
        expect(tool.input).toEqual(pair!.input);
        expect(tool.output).toEqual(pair!.output);
        expect(revealed).toEqual([[net, layers - 1], [net, 0]]);
        tool.autoSelect();
        expect(tool.canApply).toBe(true);
        expect(tool.input).toEqual(pair!.input);
        expect(tool.output).toEqual(pair!.output);
        expect(tool.error).toBe("");
      }
      const manual = { input: geometry.coil_terminals!.A.output, output: geometry.coil_terminals!.A.input };
      const chosen = { ...geometry, coil_terminals: { ...geometry.coil_terminals, A: manual } };
      expect(withAutomaticCadTerminals(chosen).coil_terminals!.A).toBe(manual);
      expect(JSON.stringify(coils)).toBe(before);
      if (layers > 2) {
        const lostSpans = structuredClone(coils);
        for (const phase of lostSpans.phases) delete phase.routed_vias;
        expect(generatedTerminalGeometry(lostSpans, layers, 1.6, .2, 2).coil_terminals?.A).toBeUndefined();
      }
    });
  }
});
