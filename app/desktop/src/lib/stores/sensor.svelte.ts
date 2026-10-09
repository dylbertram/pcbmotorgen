import {
  DEFAULT_SENSOR_CONFIG,
  type SensorConfig,
  type SensorGeometry,
} from "../types";

/** Independent state for the induction-position-sensor design workflow. */
export class SensorStore {
  config = $state<SensorConfig>({ ...DEFAULT_SENSOR_CONFIG });
  geometry = $state.raw<SensorGeometry | null>(null);
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
    this.geometry = null;
    this.error = null;
  }
}

export const sensor = new SensorStore();
