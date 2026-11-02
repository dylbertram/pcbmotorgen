import type { PreconditionLevel } from "../../types/kicad";

export function warningClasses(level: PreconditionLevel): string {
  switch (level) {
    case "error":
      return "border-rose-500/60 bg-rose-500/10 text-rose-200";
    case "warning":
      return "border-amber-500/60 bg-amber-500/10 text-amber-200";
    case "info":
      return "border-sky-500/40 bg-sky-500/10 text-sky-200";
  }
}

export function warningLabel(level: PreconditionLevel): string {
  return level.toUpperCase();
}
