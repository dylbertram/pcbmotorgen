import { describe, expect, it } from "vitest";
import { extractBaseGrade, getRemanence, MAGNET_GRADES } from "./magnets";

describe("extractBaseGrade", () => {
  it("strips thermal suffixes from the base grade", () => {
    expect(extractBaseGrade("N44H")).toBe("N44");
    expect(extractBaseGrade("N35SH")).toBe("N35");
    expect(extractBaseGrade("n42uh")).toBe("N42");
    expect(extractBaseGrade("N52")).toBe("N52");
  });

  it("passes through unknown grades untouched", () => {
    expect(extractBaseGrade("Custom")).toBe("Custom");
    expect(extractBaseGrade("Nope")).toBe("Nope");
  });
});

describe("getRemanence", () => {
  it("looks up typical remanence by base grade", () => {
    expect(getRemanence("N44")).toBe(MAGNET_GRADES.N44.br_typ_t);
    expect(getRemanence("N44H")).toBe(MAGNET_GRADES.N44.br_typ_t);
    expect(getRemanence("N52")).toBe(MAGNET_GRADES.N52.br_typ_t);
  });
});

describe("MAGNET_GRADES catalog", () => {
  it("has the six standard grades with sane Br bounds", () => {
    expect(Object.keys(MAGNET_GRADES)).toEqual(["N35", "N38", "N42", "N44", "N48", "N52"]);
    for (const g of Object.values(MAGNET_GRADES)) {
      expect(g.br_min_t).toBeLessThanOrEqual(g.br_typ_t);
      expect(g.br_typ_t).toBeLessThanOrEqual(g.br_max_t);
    }
  });
});
