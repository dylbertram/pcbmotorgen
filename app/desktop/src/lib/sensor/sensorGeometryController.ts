import { generateSensorGeometry } from "../ipc/sensor";
import type { SensorStore } from "./sensor.svelte";
import type { SensorConfig, SensorGeometry } from "../types";
import { debounce } from "../utils/debounce";
import { errorMessage } from "../utils/errorMessage";

/** Owns sensor preview requests; imported CAD remains authoritative. */
export class SensorGeometryController {
  private generation = 0;
  private schedule = debounce((generation: number, request: SensorConfig) => {
    if (generation === this.generation) void this.generate(generation, request);
  }, 150);

  constructor(
    private store: SensorStore,
    private requestGeometry: (config: SensorConfig) => Promise<SensorGeometry> = generateSensorGeometry,
  ) {}

  update(active: boolean): void {
    const generation = ++this.generation;
    if (!active) {
      this.schedule.cancel();
      this.store.loading = false;
      return;
    }
    if (this.store.cadGeometry) {
      this.schedule.cancel();
      this.store.loading = false;
      this.store.error = null;
      return;
    }
    const request = this.store.toIpc();
    this.store.loading = true;
    this.store.error = null;
    this.schedule(generation, request);
  }

  dispose(): void {
    ++this.generation;
    this.schedule.cancel();
  }

  private async generate(generation: number, request: SensorConfig): Promise<void> {
    this.store.loading = true;
    this.store.error = null;
    try {
      const result = await this.requestGeometry(request);
      if (generation === this.generation) this.store.generatedGeometry = result;
    } catch (error) {
      if (generation === this.generation) {
        this.store.generatedGeometry = null;
        this.store.error = errorMessage(error);
      }
    } finally {
      if (generation === this.generation) this.store.loading = false;
    }
  }
}
