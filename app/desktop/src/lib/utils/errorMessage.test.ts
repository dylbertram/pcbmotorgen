import { describe, expect, it } from "vitest";
import { errorMessage } from "./errorMessage";

describe("errorMessage", () => {
  it("returns the message of an Error", () => {
    expect(errorMessage(new Error("Save failed"))).toBe("Save failed");
  });

  it("stringifies non-Error rejections without adding a prefix", () => {
    expect(errorMessage("IPC unavailable")).toBe("IPC unavailable");
    expect(errorMessage(null)).toBe("null");
    expect(errorMessage(42)).toBe("42");
  });
});
