import { describe, expect, it } from "vitest";
import { warningClasses, warningLabel } from "./preflightWarning";

describe("warningClasses", () => {
  it("returns a distinct tailwind triple per severity", () => {
    const error = warningClasses("error");
    const warning = warningClasses("warning");
    const info = warningClasses("info");
    expect(error).toContain("rose");
    expect(warning).toContain("amber");
    expect(info).toContain("sky");
    const set = new Set([error, warning, info]);
    expect(set.size).toBe(3);
  });
});

describe("warningLabel", () => {
  it("uppercases the severity", () => {
    expect(warningLabel("error")).toBe("ERROR");
    expect(warningLabel("warning")).toBe("WARNING");
    expect(warningLabel("info")).toBe("INFO");
  });
});
