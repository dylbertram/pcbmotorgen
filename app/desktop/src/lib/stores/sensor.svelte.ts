import {
  DEFAULT_SENSOR_CONFIG,
  type SensorConfig,
  type SensorGeometry,
  type CadGeometry,
} from "../types";
import { cadGeometryToSensorPreview } from "../sensorCadPreview";

/** Independent state for the induction-position-sensor design workflow. */
export class SensorStore {
  config = $state<SensorConfig>({ ...DEFAULT_SENSOR_CONFIG });
  cadGeometry = $state.raw<CadGeometry | null>(null);
  generatedGeometry = $state.raw<SensorGeometry | null>(null);
  geometry = $derived(this.cadGeometry
    ? cadGeometryToSensorPreview(this.cadGeometry, this.config.via_size_mm)
    : this.generatedGeometry);
  loading = $state(false);
  error = $state<string | null>(null);

  set<K extends keyof SensorConfig>(key: K, value: SensorConfig[K]): void {
    this.config[key] = value;
  }

  toIpc(): SensorConfig {
    return { ...this.config };
  }

  apply(config?: SensorConfig | null): void {
    this.config = { ...DEFAULT_SENSOR_CONFIG, ...config };
    this.cadGeometry = null;
    this.generatedGeometry = null;
    this.error = null;
  }
}

export const sensor = new SensorStore();
