<script lang="ts">
  import { onDestroy, untrack } from "svelte";
  import type { DocumentSession } from "./lib/stores/workspace.svelte";
  import { BitsConfig, Tabs } from "bits-ui";
  import {
    evaluateForceSweep,
    generateCoils,
    generateSensorGeometry,
    fetchTravelEnvelope,
    computeFriction,
    computeHeightStack,
    analyzeDrive,
    exportSensorDxf,
    exportCadGeometryDxf,
    exportCoilsDxf,
    debounce,
  } from "./lib/ipc";
  import type {
    ForceSweepResult,
    CoilPathDto,
    FrictionBudgetDto,
    HeightStackResultDto,
    DriveAnalysis,
    SensorConfig,
    CadGeometry,
  } from "./lib/types";
  import { TABS, type TabId } from "./lib/ui";
  import { DrcController } from "./lib/stores/drc.svelte";
  import { measureTrace } from "./lib/previewGeometry";
  import { cadGeometryToPreview } from "./lib/cadPreview";
  import { saveTextToFile } from "./lib/files";
  import { geometryKey } from "./lib/cadPhases";
  import { cadMappingProblems } from "./lib/cadMapping";
  import { inferMissingCoilEnds } from "./lib/cadTerminals";

  import TabNav from "./lib/components/layout/TabNav.svelte";
  import DrcStatus from "./lib/components/layout/DrcStatus.svelte";
  import StatusIndicator from "./lib/components/layout/StatusIndicator.svelte";
  import StatusBanner from "./lib/components/ui/StatusBanner.svelte";
  import ProjectNotification from "./lib/components/ui/ProjectNotification.svelte";
  import ScrollArea from "./lib/components/ui/ScrollArea.svelte";
  import CoilPreview from "./lib/components/design/CoilPreview.svelte";
  import BackplanePanel from "./lib/components/design/BackplanePanel.svelte";
  import MagnetsPanel from "./lib/components/design/parameters/MagnetsPanel.svelte";
  import DesignTab from "./lib/components/layout/DesignTab.svelte";
  import SimulateTab from "./lib/components/layout/SimulateTab.svelte";
  import KicadDialog from "./lib/components/layout/KicadDialog.svelte";
  import CadImportDialog from "./lib/components/layout/CadImportDialog.svelte";
  import SensorTab from "./lib/components/layout/SensorTab.svelte";
  import SensorPreview from "./lib/components/design/SensorPreview.svelte";
  import ProjectVersionsDialog from "./lib/components/layout/ProjectVersionsDialog.svelte";
  import PreferencesDialog from "./lib/components/layout/PreferencesDialog.svelte";

  let { session, active }: { session: DocumentSession; active: boolean } = $props();
  // A keyed editor owns one session for its lifetime. Switching tabs never
  // swaps stores under mounted controls or in-flight requests.
  const { config, sensor: sensorStore, motion, projects, kind: designType } = untrack(() => session);

  // Session-only navigation state; none of these values enter IPC.
  let activeTab = $state<TabId>(untrack(() => session.runtime.activeTab));
  let workflowTabs = $derived(TABS.filter((tab) => designType === "motor" || tab.id !== "simulate"));
  let cadImportDialogOpen = $state(false);
  let kicadDialogOpen = $state(false);
  let exportingDxf = $state(false);
  let versionsDialogOpen = $state(false);
  let preferencesOpen = $state(false);
  let creatingVersion = $state(false);
  let versionsDialogGeneration = $state(0);

  function showVersions(creating = false): void {
    if (!active || projects.busy) return;
    creatingVersion = creating;
    versionsDialogGeneration += 1;
    versionsDialogOpen = true;
  }


  // Async result state.
  let sweep = $state<ForceSweepResult | null>(untrack(() => session.runtime.sweep));
  let coils = $state<CoilPathDto | null>(untrack(() => session.runtime.coils));
  /**
   * Geometry MEASURED from the returned coil payload (trace X extent +
   * canvas-consistent magnet-strip rest bounds). The routing braid floors
   * whole periods, so the measured trace span is intentionally shorter than
   * the configured routing domain — every preview and readout consumes THIS,
   * never the configured numbers. Null until the first payload arrives.
   */
  let friction = $state<FrictionBudgetDto | null>(untrack(() => session.runtime.friction));
  let height = $state<HeightStackResultDto | null>(untrack(() => session.runtime.height));
  let drive = $state<DriveAnalysis | null>(untrack(() => session.runtime.drive));
  let driveError = $state<string | null>(null);
  let coilPreviewExpanded = $state(false);
  let drivePending = $state(false);
  let loading = $state(false);
  let error = $state<string | null>(null);

  // Whether the current config produces a valid travel range.
  let valid = $derived(config.travel_mm > 0);

  // Shared mover position for Design constraints: the position slider
  // and the CoilPreview magnet strip both read from this store.

  // Project save/load (kata 0cgm): all persistence logic lives in the Rust
  // backend behind save_project/load_project; this store is the interface
  // half (DTO mapping + dirty tracking + dialog flows).
  // Startup has no active project yet. Catalog loading can adjust defaults,
  // but those adjustments are not user edits. Open/create/import establish
  // the first baseline when the user leaves the startup chooser.
  let activeCoils = $derived(projects.cadGeometry ? cadGeometryToPreview(projects.cadGeometry) : coils);
  let measuredTrace = $derived.by(() => measureTrace(activeCoils, config));

  export function openVersions(creating = false): void {
    showVersions(creating);
  }

  export function handleAction(action: string): void {
    if (!active || projects.busy) return;
    if (action === "export") void exportDxf();
    if (action === "kicad") kicadDialogOpen = true;
    if (action === "versions") showVersions(true);
    if (action === "browse-versions") showVersions(false);
    if (action === "settings") preferencesOpen = true;
    if (action === "import") cadImportDialogOpen = true;
  }

  // DXF currently has one format and no extra options, so go straight to Save.
  async function exportDxf(): Promise<void> {
    if (exportingDxf || projects.busy || !active) return;
    exportingDxf = true;
    projects.clearMessages();
    try {
      const cadGeometry = designType === "sensor" ? sensorStore.cadGeometry : projects.cadGeometry;
      const result = cadGeometry
        ? await exportCadGeometryDxf(cadGeometry)
        : designType === "sensor" ? await exportSensorDxf(sensorStore.toIpc()) : await exportCoilsDxf(config.toIpc());
      const path = await saveTextToFile(result.dxf_content, `${designType}-coil.dxf`, ["dxf"]);
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
      if (generation === sensorGeneration) sensorStore.generatedGeometry = result;
    } catch (e) {
      if (generation === sensorGeneration) {
        sensorStore.generatedGeometry = null;
        sensorStore.error = e instanceof Error ? e.message : String(e);
      }
    } finally {
      if (generation === sensorGeneration) sensorStore.loading = false;
    }
  }

  // Keep sensor geometry independent of motor travel and motor routing state.
  $effect(() => {
    const generation = ++sensorGeneration;
    if (!active || designType !== "sensor") {
      scheduleSensorGeometry.cancel();
      sensorStore.loading = false;
      return;
    }
    if (sensorStore.cadGeometry) {
      sensorStore.loading = false;
      sensorStore.error = null;
      return;
    }
    const request = sensorStore.toIpc();
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
    const generation = ++previewGeneration;
    if (!active || designType !== "motor") {
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
      geometryKey(projects.cadGeometry),
      config.phases,
      config.num_layers,
      config.strands_per_phase,
      config.min_trace_mm,
      config.trace_width_mm,
      config.min_space_mm,
      config.min_via_drill_mm,
      config.min_via_annular_ring_mm,
    ];
    void valid;

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

  /** An active import is always authoritative, even while its mapping is incomplete. */
  function simulationCad(): CadGeometry | null {
    return projects.cadGeometry;
  }
  const scheduleSimulation = debounce((generation: number) => {
    if (!isCurrentSimulation(generation)) return;
    void runSimulation(generation);
  }, 150);

  function isCurrentSimulation(generation: number): boolean {
    return active && activeTab === "simulate" && generation === simulationGeneration;
  }

  function clearSimulationResults(): void {
    sweep = null;
    friction = null;
    height = null;
    drive = null;
  }

  /** Opening the coil-ends panel lives in the design reflection preview. */
  function selectCoilEnds(): void {
    const proposal = projects.cadGeometry ? inferMissingCoilEnds(projects.cadGeometry) : null;
    // Review starts from the inferred pairs, so closing the preview without
    // edits keeps those ends. Ambiguous coils still require manual selection.
    if (proposal && proposal.geometry !== projects.cadGeometry) projects.setCadGeometry(proposal.geometry);
    selectTab("design");
    session.previewView.requestTerminals(proposal?.unresolved[0] ?? proposal?.pending[0]);
  }

  function useInferredEnds(): void {
    if (!projects.cadGeometry) return;
    const proposal = inferMissingCoilEnds(projects.cadGeometry);
    if (!proposal.unresolved.length) projects.setCadGeometry(proposal.geometry);
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

    // Imported copper without confirmed ends has no valid electrical model.
    // Reset rather than present numbers derived from the inferred defaults;
    // the Simulation tab shows the ends prompt in their place.
    if (projects.cadGeometry && cadMappingProblems(projects.cadGeometry, config.phases, config.min_trace_mm).length) {
      clearSimulationResults();
      driveError = null;
      error = null;
      loading = false;
      return;
    }

    loading = true;
    error = null;
    const ipc = config.toIpc();

    try {
      const results = await Promise.allSettled([
        evaluateForceSweep(ipc, simulationCad(), $state.snapshot(config.drive)),
        computeFriction(ipc),
        computeHeightStack(ipc),
      ]);

      if (!isCurrentSimulation(generation)) return;

      const [s, f, h] = results;
      // Failed panels must not show values from another input/model or feed
      // an old Kf to driver analysis. Independent successful panels remain.
      sweep = s.status === "fulfilled" ? s.value : null;
      friction = f.status === "fulfilled" ? f.value : null;
      height = h.status === "fulfilled" ? h.value : null;

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
      clearSimulationResults();
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
      config.trace_width_mm,
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
      config.drive.outer_copper_oz,
      config.drive.inner_copper_oz,
      config.drive.winding_temp_c,
      config.drive.via_plating_m,
    ];
    void JSON.stringify(config.backplane);
    void valid;
    void geometryKey(projects.cadGeometry);

    const generation = ++simulationGeneration;
    if (!active || activeTab !== "simulate") {
      scheduleSimulation.cancel();
      loading = false;
      // Invalidate an in-flight run. Tab selection releases the app-wide
      // indicator immediately; the eventual response is ignored by
      // isCurrentSimulation().
      return;
    }
    scheduleSimulation(generation);
  });

  // Driver suitability runs after each sweep (it needs the thrust constant)
  // and again when only the driver settings change, without re-running the
  // sweep. The expanded preview also needs live electrical results.
  let driveGeneration = 0;
  const scheduleDrive = debounce((generation: number) => {
    if (generation !== driveGeneration || !active || (activeTab !== "simulate" && !coilPreviewExpanded)) return;
    void runDrive(generation);
  }, 120);

  async function runDrive(generation: number): Promise<void> {
    if (!valid) {
      drive = null;
      drivePending = false;
      return;
    }
    if (projects.cadGeometry && cadMappingProblems(projects.cadGeometry, config.phases, config.min_trace_mm).length) {
      drive = null;
      driveError = null;
      drivePending = false;
      return;
    }
    const kf = sweep && sweep.current_a > 0 ? Math.abs(sweep.mean_thrust_n) / sweep.current_a : null;
    try {
      const result = await analyzeDrive(config.toIpc(), $state.snapshot(config.drive), kf, simulationCad());
      if (generation !== driveGeneration) return;
      drive = result;
      driveError = null;
      drivePending = false;
    } catch (e) {
      if (generation !== driveGeneration) return;
      drive = null;
      driveError = e instanceof Error ? e.message : String(e);
      drivePending = false;
    }
  }

  $effect(() => {
    void sweep;
    // Read all IPC inputs synchronously: reads inside the debounced async
    // run are not effect dependencies. A failed sweep must not block updates.
    void JSON.stringify(config.toIpc());
    void JSON.stringify(config.drive);
    void geometryKey(projects.cadGeometry);
    void valid;
    const generation = ++driveGeneration;
    if (!active || (activeTab !== "simulate" && !coilPreviewExpanded)) {
      scheduleDrive.cancel();
      drivePending = false;
      return;
    }
    drive = null;
    driveError = null;
    drivePending = true;
    scheduleDrive(generation);
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
      config.trace_width_mm,
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
      // Imported copper replaces the generated layout; the mapping renames
      // nets, so both live in the geometry identity.
      geometryKey(projects.cadGeometry),
    ]);
  }

  const drc = new DrcController({
    config,
    getLayoutKey: getDrcLayoutKey,
    getCadGeometry: () => projects.cadGeometry,
  });

  // A layout change invalidates the previous DRC result immediately. The
  // request id and layout key together prevent stale responses from opening
  // the export gate for a newer config.
  $effect(() => {
    if (!active || designType !== "motor") return;
    void drc.currentLayoutKey;
    drc.request();
  });

  function tabStatus(tab: TabId): { label: string; className: string } {
    if (tab === "design" && designType === "motor") {
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
    if (designType === "sensor") {
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

  onDestroy(() => {
    session.runtime = { activeTab, coils, sweep, friction, height, drive };
    ++previewGeneration;
    ++sensorGeneration;
    ++simulationGeneration;
    scheduleCoilPreview.cancel();
    scheduleSensorGeometry.cancel();
    scheduleSimulation.cancel();
    ++driveGeneration;
    scheduleDrive.cancel();
  });
</script>

<main
  class="flex min-h-0 flex-1 flex-col bg-slate-900 text-slate-100"
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
        <TabNav tabs={workflowTabs} statusFor={tabStatus}>
          {#if projects.kind === "motor"}
            <DrcStatus {drc} />
          {/if}
          <StatusIndicator loading={loading || exportingDxf} />
        </TabNav>
      </header>

      {#if projects.error}
        <div class="px-4 pt-3">
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
        </div>
      {/if}

      {#if projects.notice}
        {#key projects.notice}
          <ProjectNotification message={projects.notice} onDismiss={() => (projects.notice = null)} />
        {/key}
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

      <!-- Scroll viewports fill the space between the workflow and footer
           dividers. Insets belong inside them, so content scrolls to the edges. -->
      <div
        class="grid min-h-0 flex-1 items-start {activeTab === 'design' ? 'lg:grid-cols-[minmax(360px,0.9fr)_minmax(0,1.35fr)]' : 'lg:grid-cols-1'} lg:grid-rows-[minmax(0,1fr)] lg:items-stretch"
      >
        <!-- The desktop layout locks the page height: both columns stretch to the
             row (viewport minus header/footer) and scroll independently inside
             themselves, so the footer is always visible and the page never
             scrolls. Below lg the columns stack and the page scrolls normally. -->
        <aside
          class="relative min-w-0 min-h-0 lg:h-full {activeTab !== 'design' ? 'hidden' : ''}"
          aria-label="Coil preview panel"
        >
          <ScrollArea class="h-full min-h-0" viewportClass="p-4 lg:pr-2">
            {#if designType === "sensor"}
              <SensorPreview store={sensorStore} camera={session.camera} previewView={session.previewView} />
            {:else}
              <!-- Traces view lives here in the Design tab so layout and geometry can
                   be inspected side by side; the Simulation tab keeps its own copy. -->
              <div class="space-y-3">
                <CoilPreview {config} coils={activeCoils} {motion} bind:expanded={coilPreviewExpanded} {drive} {driveError} {drivePending} camera={session.camera} view={session.previewView} importedGeometry={projects.cadGeometry} onGeometryChange={(geometry) => projects.setCadGeometry(geometry)} />
                <BackplanePanel {config} backplaneAnalysis={height?.backplane_analysis ?? null} driveBackplane={drive?.backplane ?? null} />
                <MagnetsPanel {config} />
              </div>
            {/if}
          </ScrollArea>
        </aside>

        <div class="min-w-0 min-h-0 lg:h-full">
          <!-- Workflow panels stay mounted so component-local controls retain
               their state — Bits Tabs.Content never unmounts inactive panels, it
               toggles the hidden attribute instead. Hidden Simulation content is
               still lifecycle-gated: its IPC effects only run while this tab is
               active. Each panel fills the column and scrolls internally; the
               page height is locked so the footer always stays visible. -->
          <Tabs.Content
            value="design"
            id="panel-design"
            class="h-full"
          >
            <div hidden={designType !== "motor"} class="h-full">
               <DesignTab {config} {motion} {measuredTrace} routingDimensions={activeCoils?.routing_dimensions ?? null} cadGeometry={projects.cadGeometry} onGeometryChange={(geometry) => projects.setCadGeometry(geometry)} onImportCad={() => (cadImportDialogOpen = true)} onUseGenerated={() => projects.setCadGeometry(null)} />
            </div>
            <div hidden={designType !== "sensor"} class="h-full">
              <ScrollArea id="sensor-settings-scroll" class="h-full" viewportClass="p-4 lg:pl-2" aria-label="Sensor settings">
                <SensorTab store={sensorStore} />
              </ScrollArea>
            </div>
          </Tabs.Content>

          <Tabs.Content
            value="simulate"
            id="panel-simulate"
            class="h-full"
          >
            <ScrollArea id="simulation-scroll" class="h-full" viewportClass="p-4" aria-label="Simulation workspace">
              <SimulateTab
                onOpenPreview={() => (coilPreviewExpanded = true)}
                onConfigureWinding={() => selectTab("design")}
                {config}
                active={active && activeTab === "simulate"}
                {sweep}
                {friction}
                {height}
                {drive}
                {driveError}
                {error}
                cadGeometry={projects.cadGeometry}
                onSelectEnds={selectCoilEnds}
                onUseInferredEnds={useInferredEnds}
              />
            </ScrollArea>
          </Tabs.Content>
        </div>
      </div>

       <KicadDialog bind:open={kicadDialogOpen} {config} {projects} {drc} sensor={sensorStore} />
      {#if preferencesOpen}
        <PreferencesDialog {config} disabled={projects.busy} onClose={() => (preferencesOpen = false)} />
      {/if}

      {#if versionsDialogOpen}
        {#key versionsDialogGeneration}
          <ProjectVersionsDialog {projects} creating={creatingVersion} onClose={() => (versionsDialogOpen = false)} />
        {/key}
      {/if}

      {#if cadImportDialogOpen}
        <CadImportDialog
          {config}
          {projects}
          sensor={sensorStore}
          initialCoilType={designType}
          onClose={() => (cadImportDialogOpen = false)}
          onComplete={() => {
             selectTab("design");
             cadImportDialogOpen = false;
          }}
        />
      {/if}

      <footer
        class="shrink-0 border-t border-slate-800 px-6 py-3 text-xs text-slate-500"
      >
        {designType === "sensor" ? "Inductive position sensor" : "PCB linear motor"}
      </footer>
    </Tabs.Root>
  </BitsConfig>
</main>
