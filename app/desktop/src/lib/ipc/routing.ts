/**
 * Routing-pattern plugin IPC calls.
 *
 * Most use the standard mock gate (plain `vite dev` returns a small
 * deterministic set). `registerRoutingPlugin` is a user-actionable,
 * state-changing load — it has NO mock fallback and surfaces real
 * backend errors verbatim.
 */

import { invoke } from "@tauri-apps/api/core";
import { assertCadMapping } from "../cadMapping";
import type {
  CadGeometry,
  LinearMotorConfig,
  RoutingPatternInfo,
  RoutingParamDef,
  InstalledPlugin,
  InterferenceViolation,
} from "../types";
import { isTauriAvailable } from "./core";

/**
 * List the coil routing patterns the backend can generate (id + display
 * name). The config's `routing_pattern` field holds one of these `id`s.
 */
export async function listRoutingPatterns(): Promise<RoutingPatternInfo[]> {
  if (!isTauriAvailable()) {
    return [{ id: "infinity-braid", display_name: "Infinity Braid", min_layers: 2, layers_multiple_of: 2,
      end_type: { kind: "parameter", key: "connection", default: 0, options: [
        { value: 2, connection: "star" }, { value: 1, connection: "delta" }, { value: 0, connection: "closed" },
      ] } }];
  }
  return await invoke<RoutingPatternInfo[]>("list_routing_patterns");
}

/** Browser-mode mirror of the bundled braid's declared parameters. */
const MOCK_BRAID_PARAMS: RoutingParamDef[] = [
  {
    key: "num_strands",
    label: "Strands per period",
    description: "Number of parallel braided paths in each period.",
    param_type: "int",
    default: 5,
    min: 2,
    max: 99,
    step: 1,
  },
  {
    key: "connection",
    label: "Winding connection",
    description: "How each phase winding terminates.",
    param_type: "int",
    default: 1,
    min: 0,
    max: 2,
    step: 1,
    options: [
      { value: 1, label: "Delta" },
      { value: 2, label: "Star (wye)" },
      { value: 0, label: "Closed (legacy)" },
    ],
  },
];

/**
 * Query the user-editable parameters a routing pattern exposes. Returns
 * the declared `RoutingParamDef`s so the UI can render one editable
 * control per parameter (e.g. `num_strands`, `n_periods`).
 */
export async function routingPatternParameters(
  patternId: string,
): Promise<RoutingParamDef[]> {
  if (!isTauriAvailable()) {
    return patternId === "infinity-braid" ? MOCK_BRAID_PARAMS : [];
  }
  return await invoke<RoutingParamDef[]>("routing_pattern_parameters", {
    patternId,
  });
}

/**
 * Load and register a routing-pattern plugin (a native `cdylib`/`.dylib`
 * crate or a Python runner script) into the backend registry, probing it
 * against `config`. Returns the new pattern id.
 *
 * `name` is an optional user-chosen registry id; when `null` the plugin's
 * own id (file stem) is used.
 *
 * **No mock fallback.** A missing Tauri backend rejects explicitly
 * ("Tauri backend unavailable") and any real backend rejection is surfaced
 * verbatim to the UI.
 */
export async function registerRoutingPlugin(
  kind: "native" | "python",
  path: string,
  name: string | null,
  config: LinearMotorConfig,
): Promise<string> {
  if (!isTauriAvailable()) {
    throw new Error("Tauri backend unavailable");
  }
  return await invoke<string>("register_routing_plugin", {
    kind,
    path,
    name,
    probeConfig: config,
  });
}

/**
 * Re-register every installed plugin from the app's persistent store. Called
 * once at startup. Resolves with per-plugin load errors (empty = all ok).
 */
export async function loadInstalledPlugins(): Promise<string[]> {
  if (!isTauriAvailable()) return [];
  return await invoke<string[]>("load_installed_plugins");
}

/**
 * List the routing-pattern generators in the app's persistent store. Browser
 * mode has no store, so it reports none.
 */
export async function listInstalledPlugins(): Promise<InstalledPlugin[]> {
  if (!isTauriAvailable()) return [];
  return await invoke<InstalledPlugin[]>("list_installed_plugins");
}

/**
 * Remove an installed routing-pattern generator from the persistent store and
 * the runtime registry. Unlike the read paths this changes state, so there is
 * no mock fallback: browser mode rejects explicitly.
 */
export async function removeRoutingPlugin(id: string): Promise<void> {
  if (!isTauriAvailable()) {
    throw new Error("Tauri backend unavailable");
  }
  await invoke("remove_routing_plugin", { id });
}

/**
 * Run the core's DRC interference checks (clearance + via-pad) on the
 * coils the current pattern produces, using the configured trace / via
 * sizes. Returns the violations (empty = clear).
 */
export async function checkCoilInterference(
  config: LinearMotorConfig,
  cadGeometry: CadGeometry | null = null,
): Promise<InterferenceViolation[]> {
  assertCadMapping(cadGeometry, config);
  if (!isTauriAvailable()) return [];
  return await invoke<InterferenceViolation[]>("check_coil_interference", {
    config,
    cadGeometry,
  });
}
