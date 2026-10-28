import { describe, it, expect } from "vitest";
import { generatedTerminalGeometry } from "./generatedTerminalGeometry";
import type { CoilPathDto } from "./types";

describe("generated display depths match native physics", () => {
  it("keeps layer0 at PCB top and later layers at negative physical depths", () => {
    const coils = { phases: [] } as unknown as CoilPathDto;
    expect(generatedTerminalGeometry(coils, 3, .8, .2).layer_z_mm).toEqual([0, -.4, -.8]);
    expect(generatedTerminalGeometry(coils, 1, .8, .2).layer_z_mm).toEqual([0]);
  });
});
