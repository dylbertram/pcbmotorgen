import { describe, expect, it } from "vitest";
import authoringGuideMd from "../../../../../crates/pcbmotorgen-routing/docs/routing-pattern-authoring.md?raw";
import apiReferenceMd from "../../../../../crates/pcbmotorgen-routing/docs/API.md?raw";
import exampleRunnerPy from "../../../../../crates/pcbmotorgen-export/scripts/pattern_runners/example_runner.py?raw";
import { GUIDE_TABS } from "./docs";
import { markdownToHtml } from "./markdown";

const GUIDE_SOURCES = { authoringGuideMd, apiReferenceMd, exampleRunnerPy };

/**
 * The guide is bundled verbatim from the routing crate docs at build time.
 * These tests pin the CONTRACT-CRITICAL content that must be present: if a
 * doc loses a section (or the import path silently breaks to a stub), these
 * fail. Raw `?raw` imports make a MISSING file a build error — these tests
 * additionally guard against a present-but-gutted file.
 */
describe("bundled guide docs (single source of truth)", () => {
  it("exposes the three guide tabs", () => {
    expect(GUIDE_TABS.map((t) => t.id)).toEqual(["authoring", "api", "example"]);
    for (const tab of GUIDE_TABS) {
      expect(tab.label.length).toBeGreaterThan(0);
      expect(tab.html).toContain("<h1>");
    }
  });

  it("renders the bundled source documents in their respective tabs", () => {
    expect(GUIDE_TABS.find((t) => t.id === "authoring")?.html).toBe(markdownToHtml(authoringGuideMd));
    expect(GUIDE_TABS.find((t) => t.id === "api")?.html).toBe(markdownToHtml(apiReferenceMd));
    expect(GUIDE_TABS.find((t) => t.id === "example")?.html).toContain(
      markdownToHtml(`\`\`\`python\n${exampleRunnerPy.replace(/\s+$/, "")}\n\`\`\``),
    );
  });

  it("authoring guide covers the contract & units (mm, x = travel, y = width)", () => {
    expect(GUIDE_SOURCES.authoringGuideMd).toContain("millimetres");
    expect(GUIDE_SOURCES.authoringGuideMd).toContain("x = travel axis, y = across width");
    expect(GUIDE_SOURCES.authoringGuideMd).toContain("`0 .. num_layers-1`");
  });

  it("authoring guide covers the RoutingResult schema incl. hzs2 + htcq fields", () => {
    expect(GUIDE_SOURCES.authoringGuideMd).toContain("phase_bands");
    expect(GUIDE_SOURCES.authoringGuideMd).toContain("io_pads");
    expect(GUIDE_SOURCES.authoringGuideMd).toContain("io_traces");
    expect(GUIDE_SOURCES.authoringGuideMd).toContain("pole_regions");
  });

  it("documents the landed we8r layer-range + multiple_of constraints (no placeholders)", () => {
    const src = GUIDE_SOURCES.authoringGuideMd;
    expect(src).toContain("min_layers");
    expect(src).toContain("max_layers");
    expect(src).toContain("layers_multiple_of");
    expect(src).toContain("multiple_of");
    expect(src.toLowerCase()).not.toContain("coming soon");
  });

  it("documents the Rust cdylib path and the Python stdin/stdout contract", () => {
    const src = GUIDE_SOURCES.authoringGuideMd;
    expect(src).toContain("pcbmotorgen_routing_plugin_create");
    expect(src).toContain('crate-type = ["cdylib"]');
    expect(src).toContain("pcbmotorgen_ROUTING_PLUGIN_API");
    expect(src).toContain("--metadata");
    expect(src).toContain("nothing else");
  });

  it("documents rejected-not-sanitised validation and the install flow", () => {
    const src = GUIDE_SOURCES.authoringGuideMd;
    expect(src).toContain("rejected");
    expect(src).toContain("never silently patched");
    expect(src).toContain("app_data/plugins/");
    expect(src).toContain("Browse…");
  });

  it("API reference includes the normative sections (units, 5.2, 5.3, 6, 6.1)", () => {
    const src = GUIDE_SOURCES.apiReferenceMd;
    expect(src).toContain("## 2. Units and coordinate conventions");
    expect(src).toContain("### 5.2 Phase bands");
    expect(src).toContain("### 5.3 IO elements");
    expect(src).toContain("## 6. The `RoutingPattern` trait");
    expect(src).toContain("### 6.1 Parameters");
    expect(src).toContain("Layers_multiple_of".toLowerCase());
  });

  it("worked example bundles the reference runner verbatim", () => {
    expect(GUIDE_SOURCES.exampleRunnerPy).toContain('"id": "example-runner"');
    expect(GUIDE_SOURCES.exampleRunnerPy).toContain("def generate(ctx: dict) -> dict:");
    expect(GUIDE_SOURCES.exampleRunnerPy).toContain("if \"--metadata\" in sys.argv:");
    const exampleTab = GUIDE_TABS.find((t) => t.id === "example");
    // The runner source renders inside one fenced <pre><code> block.
    expect(exampleTab?.html).toContain('"key": "conductor_offset"');
    expect(exampleTab?.html).toContain("<pre><code class=\"language-python\">");
  });

  it("renders strictly-escaped HTML (no raw pass-through anywhere)", () => {
    for (const tab of GUIDE_TABS) {
      expect(tab.html).not.toMatch(/<script/i);
      expect(tab.html).not.toMatch(/<img/i);
      expect(tab.html).not.toMatch(/onerror=/i);
    }
  });
});
