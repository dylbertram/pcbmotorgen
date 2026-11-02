import { describe, expect, it } from "vitest";
import { baseName, parentDirectory } from "./paths";

describe("path display helpers", () => {
  it.each([
    ["/designs/motor.pmmotor", "motor.pmmotor", "/designs/"],
    ["C:\\designs\\sensor.pmsensor", "sensor.pmsensor", "C:\\designs\\"],
    ["C:\\designs/motor.pmmotor", "motor.pmmotor", "C:\\designs/"],
    ["/motor.pmmotor", "motor.pmmotor", "/"],
    ["motor.pmmotor", "motor.pmmotor", null],
    ["/designs/", "", "/designs/"],
    ["", "", null],
  ])("extracts names and directories from %s", (path, name, directory) => {
    expect(baseName(path)).toBe(name);
    expect(parentDirectory(path)).toBe(directory);
  });
});
