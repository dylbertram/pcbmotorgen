<script lang="ts">
  import { config } from "./lib/stores/config.svelte";
  import { BitsConfig, Tabs } from "bits-ui";
  import {
    evaluateForceSweep,
    generateCoils,
    generateSensorGeometry,
    fetchTravelEnvelope,
    computeFriction,
    computePowerBudget,
    computeHeightStack,
    computeStackup,
    bindProjectMenuActions,
    exportCadGeometryDxf,
    exportCoilsDxf,
    debounce,
  } from "./lib/ipc";
  import type {
    ForceSweepResult,
    CoilPathDto,
    FrictionBudgetDto,
    PowerBudgetDto,
    HeightStackResultDto,
    StackupResultDto,
    SensorConfig,
  } from "./lib/types";
  import { TABS, type TabId } from "./lib/ui";
  import { DrcController } from "./lib/stores/drc.svelte";
  import { MotionStore } from "./lib/stores/motion.svelte";
  import { ProjectStore } from "./lib/stores/project.svelte";
  import { sensor as sensorStore } from "./lib/stores/sensor.svelte";
  import { recentFiles } from "./lib/stores/recentFiles.svelte";
  import { measureTrace } from "./lib/previewGeometry";
  import { cadGeometryToPreview } from "./lib/cadPreview";
  import { saveTextToFile } from "./lib/files";

  import TabNav from "./lib/components/layout/TabNav.svelte";
  import TitleBar from "./lib/components/layout/TitleBar.svelte";
  import StatusBanner from "./lib/components/ui/StatusBanner.svelte";
  import ScrollArea from "./lib/components/ui/ScrollArea.svelte";
  import TravelDiagram from "./lib/components/design/TravelDiagram.svelte";
  import CoilPreview from "./lib/components/design/CoilPreview.svelte";
  import DesignDimensions from "./lib/components/design/DesignDimensions.svelte";
  import DesignTab from "./lib/components/layout/DesignTab.svelte";
  import SimulateTab from "./lib/components/layout/SimulateTab.svelte";
  import KicadDialog from "./lib/components/layout/KicadDialog.svelte";
  import StartupScreen from "./lib/components/layout/StartupScreen.svelte";
  import CadImportDialog from "./lib/components/layout/CadImportDialog.svelte";
  import SensorTab from "./lib/components/layout/SensorTab.svelte";
  import SensorPreview from "./lib/components/design/SensorPreview.svelte";

  // Session-only navigation state; none of these values enter IPC.
  let activeTab = $state<TabId>("design");
  let startupOpen = $state(true);
  let startupRecentLoading = $state(true);
  let cadImportDialogOpen = $state(false);
  let kicadDialogOpen = $state(false);
  let exportingDxf = $state(false);

  // App init: populate the routing-pattern selector + magnet-grade reference
  // from the backend. Fire-and-forget — failures are swallowed inside the
  // stores (the static TS tables remain as offline fallbacks).
  config.loadRoutingPatterns();
  config.loadMagnetGrades();

  // Async result state.
  let sweep = $state<ForceSweepResult | null>(null);
  let coils = $state<CoilPathDto | null>(null);
  /**
   * Geometry MEASURED from the returned coil payload (trace X extent +
   * canvas-consistent magnet-strip rest bounds). The routing braid floors
   * whole periods, so the measured trace span is intentionally shorter than
   * the configured routing domain — every preview and readout consumes THIS,
   * never the configured numbers. Null until the first payload arrives.
   */
  let friction = $state<FrictionBudgetDto | null>(null);
  let power = $state<PowerBudgetDto | null>(null);
  let height = $state<HeightStackResultDto | null>(null);
  let stackup = $state<StackupResultDto | null>(null);
  let loading = $state(false);
  let error = $state<string | null>(null);

  // Whether the current config produces a valid travel range.
  let valid = $derived(config.travel_mm > 0);

  // Shared mover position for the design reflection: the TravelDiagram slider
  // and the CoilPreview magnet strip both read from this store.
  const motion = new MotionStore(config);

  // Project save/load (kata 0cgm): all persistence logic lives in the Rust
  // backend behind save_project/load_project; this store is the interface
  // half (DTO mapping + dirty tracking + dialog flows).
  const projects = new ProjectStore(config, motion, recentFiles, sensorStore);
  projects.markClean();
  let activeCoils = $derived(projects.cadGeometry ? cadGeometryToPreview(projects.cadGeometry) : coils);
  let measuredTrace = $derived.by(() => measureTrace(activeCoils, config));

  // Open Recent (kata eap8): lazily load the persisted list and build the
  // native submenu from disk truth (the load prunes vanished entries).
  // Load recents before the startup chooser offers its recent-project list.
  // Best effort — a recents hiccup must never block startup.
  void recentFiles
    .load()
    .catch(() => undefined)
    .finally(() => (startupRecentLoading = false));

  // Native File menu: menu clicks land here as Tauri events
  // and dispatch into the same store flows. The store's busy guard
  // serializes overlapping menu events.
  $effect(() => {
    const unbind = bindProjectMenuActions({
      newProject: () => {
        void projects.newProject().then((created) => {
          if (!created) return;
          // Clear a focused field's local draft after the stores are reset.
          if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
          startupOpen = false;
          cadImportDialogOpen = false;
          kicadDialogOpen = false;
          clearSimulationResults();
          selectTab("design");
        });
      },
      exportDxf: () => void exportDxf(),
      sendKicad: () => (kicadDialogOpen = true),
      open: () => {
        void projects.open().then((opened) => {
          if (opened) startupOpen = false;
        });
      },
      save: () => void projects.save(false),
      saveAs: () => void projects.save(true),
      importCad: () => (cadImportDialogOpen = true),
      openRecent: (path) => {
        // Open-recent access point: refresh menu truth (the entry is pruned
        // when its file vanished) before dispatching into the shared open
        // flow — a vanished file surfaces the existing "Open failed — …"
        // error banner. Both calls fail-open; no catch needed.
        void recentFiles.dropMissing(path)
          .then(() => projects.openPath(path))
          .then((opened) => {
            if (opened) startupOpen = false;
          });
      },
      clearRecent: () => void recentFiles.clear(),
    });
    return () => {
      void unbind.then((done) => done());
    };
  });

  // DXF currently has one format and no extra options, so go straight to Save.
  async function exportDxf(): Promise<void> {
    if (exportingDxf || projects.busy || startupOpen) return;
    exportingDxf = true;
    projects.clearMessages();
    try {
      const result = projects.cadGeometry
        ? await exportCadGeometryDxf(projects.cadGeometry)
        : await exportCoilsDxf(config.toIpc());
      const path = await saveTextToFile(result.dxf_content, "coils.dxf", ["dxf"]);
      if (path) projects.notice = `Exported DXF to ${path}.`;
    } catch (e) {
      projects.error = `DXF export failed: ${e instanceof Error ? e.message : String(e)}`;
    } finally {
      exportingDxf = false;
    }
  }

  // -----------------------------------------------------------------------
  // Design preview generation
  // -----------------------------------------------------------------------
  // Coil geometry is useful outside the Simulation tab, so it has its own
  // request stream. A generation id prevents a slow response for an older
  // config from replacing a newer preview. The preview keeps its last good
  // result while a new request is pending or fails.
  let previewGeneration = 0;
  const scheduleCoilPreview = debounce((generation: number) => {
    if (generation !== previewGeneration) return;
    if (!valid) {
      coils = null;
      return;
    }
    void updateCoilPreview(generation, config.toIpc());
  }, 150);

  let sensorGeneration = 0;
  const scheduleSensorGeometry = debounce(
    (generation: number, request: SensorConfig) => {
      if (generation !== sensorGeneration) return;
      void updateSensorGeometry(generation, request);
    },
    150,
  );

  async function updateSensorGeometry(
    generation: number,
    request: SensorConfig,
  ): Promise<void> {
    sensorStore.loading = true;
    sensorStore.error = null;
    try {
      const result = await generateSensorGeometry(request);
      if (generation === sensorGeneration) sensorStore.geometry = result;
    } catch (e) {
      if (generation === sensorGeneration) {
        sensorStore.geometry = null;
        sensorStore.error = e instanceof Error ? e.message : String(e);
      }
    } finally {
      if (generation === sensorGeneration) sensorStore.loading = false;
    }
  }

  // Keep sensor geometry independent of motor travel and motor routing state.
  $effect(() => {
    const request = sensorStore.toIpc();
    const generation = ++sensorGeneration;
    sensorStore.loading = true;
    sensorStore.error = null;
    scheduleSensorGeometry(generation, request);
  });

  async function updateCoilPreview(
    generation: number,
    ipc: ReturnType<typeof config.toIpc>,
  ): Promise<void> {
    try {
      const result = await generateCoils(ipc);
      if (generation === previewGeneration) coils = result;
    } catch {
      // Keep the previous preview visible. A transient generation failure
      // must not make the design reflection depend on simulation state.
    }
    // Equilibrium travel envelope (stable rest positions of the mover
    // centre). Fetched on the same debounced/generation-guarded stream; a
    // failure keeps the previous envelope (or the flagged placeholder —
    // MotionStore raises "travel envelope unavailable", kata ab30).
    try {
      const env = await fetchTravelEnvelope(ipc);
      if (generation === previewGeneration) motion.setEnvelope(env);
    } catch {
      // Keep the previous envelope — bounds stay at their last good values.
    }
  }

  // Generate the Design-tab reflection when geometry or routing inputs change.
  // This effect intentionally runs regardless of the active workflow tab.
  $effect(() => {
    if (startupOpen) {
      scheduleCoilPreview.cancel();
      return;
    }
    void [
      config.desired_travel_mm,
      config.active_area_length_mm,
      config.active_area_width_mm,
      config.magnet_count,
      config.magnet_width_mm,
      config.magnet_gap_mm,
      config.electrical_pitch_mm,
      config.routing_pattern,
      config.routing_params_version,
      config.phases,
      config.num_layers,
      config.strands_per_phase,
      config.min_trace_mm,
      config.min_space_mm,
      config.min_via_drill_mm,
      config.min_via_annular_ring_mm,
    ];
    void valid;

    const generation = ++previewGeneration;
    scheduleCoilPreview(generation);
  });

  // -----------------------------------------------------------------------
  // Simulation-tab scheduling
  // -----------------------------------------------------------------------
  // Simulation is demand-driven: entering the Simulation tab or changing a
  // watched input while it is active schedules one run. The generation id
  // gates both the debounce callback and all result writes, including work
  // that was already in flight when the user changed tabs.
  let simulationGeneration = 0;
  const scheduleSimulation = debounce((generation: number) => {
    if (!isCurrentSimulation(generation)) return;
    void runSimulation(generation);
  }, 150);

  function isCurrentSimulation(generation: number): boolean {
    return activeTab === "simulate" && generation === simulationGeneration;
  }

  function clearSimulationResults(): void {
    sweep = null;
    friction = null;
    power = null;
    height = null;
    stackup = null;
  }

  async function runSimulation(generation: number): Promise<void> {
    if (!isCurrentSimulation(generation)) return;

    // Invalid geometry is a deliberate reset, not a backend failure. Keep
    // valid results while editing, but do not run any simulation IPC call.
    if (!valid) {
      clearSimulationResults();
      error = null;
      loading = false;
      return;
    }

    loading = true;
    error = null;
    const ipc = config.toIpc();

    try {
      const results = await Promise.allSettled([
        evaluateForceSweep(ipc),
        computeFriction(ipc),
        computePowerBudget(ipc),
        computeHeightStack(ipc),
        computeStackup(ipc),
      ]);

      if (!isCurrentSimulation(generation)) return;

      const [s, f, p, h, st] = results;
      // Apply each successful result independently. A failed calculation does
      // not erase the last good value from the other simulation panels.
      if (s.status === "fulfilled") sweep = s.value;
      if (f.status === "fulfilled") friction = f.value;
      if (p.status === "fulfilled") power = p.value;
      if (h.status === "fulfilled") height = h.value;
      if (st.status === "fulfilled") stackup = st.value;

      const reasons = results
        .filter(
          (result): result is PromiseRejectedResult =>
            result.status === "rejected",
        )
        .map((result) =>
          result.reason instanceof Error
            ? result.reason.message
            : String(result.reason),
        );
      error = reasons.length ? reasons.join("  ·  ") : null;
    } catch (e) {
      if (!isCurrentSimulation(generation)) return;
      error = e instanceof Error ? e.message : String(e);
    } finally {
      if (isCurrentSimulation(generation)) loading = false;
    }
  }

  // Touch every input used by the simulation calls. The active-tab check is
  // intentionally inside the effect so config changes outside Simulation
  // only invalidate/cancel a pending run; they never invoke simulation IPC.
  $effect(() => {
    void [
      config.desired_travel_mm,
      config.active_area_length_mm,
      config.active_area_width_mm,
      config.magnet_count,
      config.magnet_width_mm,
      config.magnet_gap_mm,
      config.electrical_pitch_mm,
      config.magnet_height_mm,
      config.magnet_cross_width_mm,
      config.magnet_remanence_t,
      config.magnet_grade,
      config.air_gap_mm,
      config.routing_pattern,
      config.routing_params_version,
      config.phases,
      config.num_layers,
      config.strands_per_phase,
      config.max_current_a,
      config.supply_voltage_v,
      config.pcb_thickness_mm,
      config.min_trace_mm,
      config.min_space_mm,
      config.min_via_drill_mm,
      config.min_via_annular_ring_mm,
      config.max_layers,
      config.drive_frequency_hz,
      config.max_temperature_rise_c,
      config.target_force_n,
      config.peak_force_n,
      config.friction_n,
      config.carriage_mass_kg,
      config.max_accel_m_s2,
      config.capacitor_bank_uf,
      config.commutation,
      config.n_positions,
      config.meshing,
    ];
    void valid;

    const generation = ++simulationGeneration;
    if (activeTab !== "simulate") {
      scheduleSimulation.cancel();
      // Invalidate an in-flight run. Tab selection releases the app-wide
      // indicator immediately; the eventual response is ignored by
      // isCurrentSimulation().
      return;
    }
    scheduleSimulation(generation);
  });

  // -----------------------------------------------------------------------
  // App-owned DRC controller
  // -----------------------------------------------------------------------
  // Layout fingerprint: the inputs that determine where the generated
  // traces can be placed (preserved verbatim from the inline controller).
  function getDrcLayoutKey(): string {
    return JSON.stringify([
      config.routing_pattern,
      config.routing_params_version,
      config.num_layers,
      config.min_trace_mm,
      config.min_space_mm,
      config.min_via_drill_mm,
      config.min_via_annular_ring_mm,
      config.strands_per_phase,
      config.magnet_count,
      config.magnet_width_mm,
      config.magnet_gap_mm,
      config.phases,
      config.active_area_length_mm,
      config.active_area_width_mm,
    ]);
  }

  const drc = new DrcController({ config, getLayoutKey: getDrcLayoutKey });

  // A layout change invalidates the previous DRC result immediately. The
  // request id and layout key together prevent stale responses from opening
  // the export gate for a newer config.
  $effect(() => {
    if (startupOpen) return;
    void drc.currentLayoutKey;
    drc.request();
  });

  function tabStatus(tab: TabId): { label: string; className: string } {
    if (tab === "design") {
      return valid
        ? { label: "ready", className: "text-emerald-300" }
        : { label: "needs attention", className: "text-rose-300" };
    }
    if (tab === "simulate") {
      if (!valid) return { label: "blocked", className: "text-rose-300" };
      return loading
        ? { label: "updating", className: "text-amber-300" }
        : { label: "ready", className: "text-emerald-300" };
    }
    if (tab === "sensor") {
      if (sensorStore.error) {
        return { label: "needs attention", className: "text-rose-300" };
      }
      return sensorStore.loading || !sensorStore.geometry
        ? { label: "updating", className: "text-amber-300" }
        : { label: "ready", className: "text-emerald-300" };
    }
    return { label: "ready", className: "text-emerald-300" };
  }

  function selectTab(tab: TabId): void {
    activeTab = tab;
    if (tab !== "simulate") loading = false;
  }
</script>

<main
  class="flex min-h-screen flex-col bg-slate-900 text-slate-100 lg:h-screen lg:overflow-hidden"
>
  <!-- BitsConfig centralizes the portal target for every Bits portal
       (dialogs, selects, tooltips) in one place. -->
  <BitsConfig defaultPortalTo="body" defaultLocale="en-US">
    <!-- Tabs.Root renders its own wrapper element, so the main column's
         flex layout (grow + shrink floor) lives on it. -->
    <Tabs.Root
      value={activeTab}
      onValueChange={(v) => selectTab(v as TabId)}
      class="flex min-h-0 flex-1 flex-col"
    >
      <header class="shrink-0 bg-slate-900">
        <TitleBar {projects} loading={loading || exportingDxf} {drc} />
        <TabNav tabs={TABS} statusFor={tabStatus} />
      </header>

      {#if projects.error || projects.notice}
        <div class="px-4 pt-3">
          {#if projects.error}
            <StatusBanner level="error">
              <div class="flex items-start justify-between gap-3">
                <p>{projects.error}</p>
                <button
                  type="button"
                  class="shrink-0 underline underline-offset-2 hover:brightness-125"
                  onclick={() => projects.clearMessages()}>Dismiss</button
                >
              </div>
            </StatusBanner>
          {:else if projects.notice}
            <StatusBanner level="info">
              <div class="flex items-start justify-between gap-3">
                <p>{projects.notice}</p>
                <button
                  type="button"
                  class="shrink-0 underline underline-offset-2 hover:brightness-125"
                  onclick={() => projects.clearMessages()}>Dismiss</button
                >
              </div>
            </StatusBanner>
          {/if}
        </div>
      {/if}

      {#if projects.loadIssues}
        <div class="px-4 pt-3">
          <StatusBanner
            level={projects.loadIssues.errors.length > 0 ? "error" : "warning"}
          >
            <div>
              <p class="font-medium">
                The restored design has
                {projects.loadIssues.errors.length} error(s) and
                {projects.loadIssues.warnings.length} warning(s):
              </p>
              <ul class="mt-1 list-disc pl-5">
                {#each projects.loadIssues.errors as message (message)}
                  <li>{message}</li>
                {/each}
                {#each projects.loadIssues.warnings as message (message)}
                  <li>{message}</li>
                {/each}
              </ul>
            </div>
          </StatusBanner>
        </div>
      {/if}

      <!-- The reflection stays mounted beside every workflow panel. On desktop
           only the settings/content column scrolls; on small screens the columns
           stack so the reflection remains available above the active panel. -->
      <div
        class="grid min-h-0 flex-1 items-start gap-4 px-4 pb-4 lg:grid-cols-[minmax(360px,0.9fr)_minmax(0,1.35fr)] lg:grid-rows-[minmax(0,1fr)] lg:items-stretch lg:pb-0 lg:pr-0"
      >
        <!-- The desktop layout locks the page height: both columns stretch to the
             row (viewport minus header/footer) and scroll independently inside
             themselves, so the footer is always visible and the page never
             scrolls. Below lg the columns stack and the page scrolls normally. -->
        <aside
        class="relative min-w-0 min-h-0 lg:h-full lg:pt-4 lg:pb-4 lg:pr-2"
          aria-label="Persistent design reflection"
        >
          <ScrollArea class="h-full min-h-0">
            {#if activeTab === "sensor"}
              <SensorPreview store={sensorStore} />
            {:else}
              <TravelDiagram {config} {motion} {measuredTrace} />
              <!-- Traces view lives here in the Design tab so layout and geometry can
                   be inspected side by side; the Simulation tab keeps its own copy. -->
              <div class="mt-3 space-y-3">
                <CoilPreview {config} coils={activeCoils} {motion} />
                <DesignDimensions
                  {config}
                  measuredTraceLengthMm={measuredTrace?.traceLengthMm ?? null}
                  routingDimensions={activeCoils?.routing_dimensions ?? null}
                  cadGeometryActive={projects.cadGeometry !== null}
                />
              </div>
            {/if}
          </ScrollArea>
        </aside>

        <div class="min-w-0 min-h-0 lg:h-full">
          <!-- All three panels stay mounted so component-local controls retain
               their state — Bits Tabs.Content never unmounts inactive panels, it
               toggles the hidden attribute instead. Hidden Simulation content is
               still lifecycle-gated: its IPC effects only run while this tab is
               active. Each panel fills the column and scrolls internally; the
               page height is locked so the footer always stays visible. -->
          <Tabs.Content
            value="design"
            id="panel-design"
            class="h-full p-4 lg:pr-0"
          >
              <DesignTab {config} cadGeometry={projects.cadGeometry} />
          </Tabs.Content>

          <Tabs.Content
            value="simulate"
            id="panel-simulate"
            class="h-full overflow-y-auto p-4 lg:pr-0"
          >
            <SimulateTab
              {config}
              active={activeTab === "simulate"}
              {sweep}
              {friction}
              {power}
              {height}
               {stackup}
               {error}
               cadGeometryActive={projects.cadGeometry !== null}
            />
          </Tabs.Content>

          <Tabs.Content
            value="sensor"
            id="panel-sensor"
            class="h-full overflow-y-auto p-4 lg:pr-0"
          >
            <SensorTab store={sensorStore} />
          </Tabs.Content>
        </div>
      </div>

      {#if startupOpen}
        <StartupScreen
          {config}
          {projects}
          {recentFiles}
          recentLoading={startupRecentLoading}
          onComplete={() => (startupOpen = false)}
          onImportCad={() => (cadImportDialogOpen = true)}
        />
      {/if}

      <KicadDialog bind:open={kicadDialogOpen} {config} {projects} {drc} />

      {#if cadImportDialogOpen}
        <CadImportDialog
          {config}
          {projects}
          onClose={() => (cadImportDialogOpen = false)}
          onComplete={() => {
            cadImportDialogOpen = false;
            startupOpen = false;
          }}
        />
      {/if}

      <footer
        class="shrink-0 border-t border-slate-800 px-6 py-3 text-xs text-slate-500"
      >
        Motor physics and routing plus an independent two-layer induction sensor workflow.
      </footer>
    </Tabs.Root>
  </BitsConfig>
</main>
