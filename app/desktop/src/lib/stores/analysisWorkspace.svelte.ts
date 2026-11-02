/** View-only editor group, owned by its source document, never serialised. */
export class AnalysisWorkspace {
  driverCheckOpen = $state(false);
  focusedGroup = $state<"design" | "driver">("design");
  leftPercent = $state(55);
  simulationView = $state<"move" | "force" | "fields" | "advanced">("move");

  openDriverCheck(): void {
    this.driverCheckOpen = true;
    this.focusedGroup = "driver";
  }

  closeDriverCheck(): void {
    this.driverCheckOpen = false;
    this.focusedGroup = "design";
  }

  resize(value: number): void {
    if (Number.isFinite(value)) this.leftPercent = Math.min(75, Math.max(30, value));
  }
}
