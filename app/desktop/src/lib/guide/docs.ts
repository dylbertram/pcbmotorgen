/** Bundle the routing guide and its reference runner directly from the crates.
 * Missing raw imports fail the build; vite.config.ts allows them in dev mode.
 */

import authoringGuideMd from "../../../../../crates/pcbmotorgen-routing/docs/routing-pattern-authoring.md?raw";
import apiReferenceMd from "../../../../../crates/pcbmotorgen-routing/docs/API.md?raw";
import exampleRunnerPy from "../../../../../crates/pcbmotorgen-export/scripts/pattern_runners/example_runner.py?raw";

import { markdownToHtml } from "./markdown";

export interface GuideTab {
  /** Stable tab id (also used as the DOM key). */
  id: string;
  /** Short tab label. */
  label: string;
  /** Accessible name of the tab panel content (first heading). */
  title: string;
  /** Pre-rendered, escaped HTML for the tab body (safe for {@html}). */
  html: string;
}

/**
 * The reference Python runner, bundled VERBATIM as the guide's worked
 * example. It is the same file the authoring guide points at
 * (`scripts/pattern_runners/example_runner.py`), displayed inside a fenced
 * code block — the only glue here is the framing sentence and the path
 * label, not any contract content.
 */
function workedExampleHtml(): string {
  const md = [
    "# Worked example — reference Python runner",
    "",
    "The reference runner below is bundled verbatim from",
    "`crates/pcbmotorgen-export/scripts/pattern_runners/example_runner.py`.",
    "It is a fully valid, minimal plugin: copy it and grow your generator",
    "from there. Note the two modes — the strict stdin → stdout",
    "`RoutingResult` contract, and the optional `--metadata` block.",
    "",
    "```python",
    exampleRunnerPy.replace(/\s+$/, ""),
    "```",
  ].join("\n");
  return markdownToHtml(md);
}

/** The bundled guide tabs, rendered once at module load. */
export const GUIDE_TABS: GuideTab[] = [
  {
    id: "authoring",
    label: "Authoring guide",
    title: "Routing-Pattern Plugin Authoring Guide",
    html: markdownToHtml(authoringGuideMd),
  },
  {
    id: "api",
    label: "API reference",
    title: "pcbmotorgen-routing API",
    html: markdownToHtml(apiReferenceMd),
  },
  {
    id: "example",
    label: "Worked example",
    title: "Worked example — reference Python runner",
    html: workedExampleHtml(),
  },
];
