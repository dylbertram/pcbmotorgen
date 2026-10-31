import type { GeneratorEndType, RoutingPatternInfo, WindingConnection } from "./types/routing";

export function windingConnectionLabel(connection: WindingConnection): string {
  return connection === "star" ? "Star (Wye)" : connection === "delta" ? "Delta" : "Closed (legacy)";
}

export function generatorConnection(metadata: GeneratorEndType | null | undefined, params: Record<string, number>): WindingConnection | null {
  if (!metadata) return null;
  if (metadata.kind === "fixed") return metadata.connection;
  const value = params[metadata.key] ?? metadata.default;
  return metadata.options.find((option) => option.value === value)?.connection ?? null;
}

/** UI-only source keys. Persist the original pattern ID and numeric parameter. */
export interface RoutingSource {
  value: string;
  label: string;
  patternId: string;
  parameter: { key: string; value: number } | null;
}

export function routingSources(patterns: RoutingPatternInfo[], activeId: string, params: Record<string, number>): RoutingSource[] {
  return patterns.flatMap<RoutingSource>((pattern) => {
    const endType = pattern.end_type;
    if (endType?.kind === "parameter") {
      const current = params[endType.key] ?? endType.default;
      const sources: RoutingSource[] = endType.options.filter((option) => option.connection !== "closed" || (activeId === pattern.id && current === option.value))
        .map((option) => ({
          value: JSON.stringify([pattern.id, option.value]),
          label: `${pattern.display_name} - ${windingConnectionLabel(option.connection)}`,
          patternId: pattern.id,
          parameter: { key: endType.key, value: option.value },
        }));
      if (activeId === pattern.id && !endType.options.some((option) => option.value === current)) {
        sources.push({ value: JSON.stringify([pattern.id, current]), label: `${pattern.display_name} - Unknown connection (${current})`, patternId: pattern.id, parameter: { key: endType.key, value: current } });
      }
      return sources;
    }
    return [{ value: pattern.id, label: endType?.kind === "fixed" ? `${pattern.display_name} - ${windingConnectionLabel(endType.connection)}` : pattern.display_name, patternId: pattern.id, parameter: null }];
  });
}
