//! Coil-writing orchestration on [`super::BoardHandle`].
//!
//! [`write_coils`](super::BoardHandle::write_coils) converts the coil
//! geometry to KiCad board items via [`coils_to_board_items`], opens a
//! [`Commit`], creates the items, ends the commit, and tallies the per-item
//! outcomes via [`super::tally::tally_item_results`]. The dry-run variant
//! skips all IPC traffic.

use pcbmotorgen_dfm::DesignRules;
use pcbmotorgen_routing::{PhaseCoil, RoutingResult, SensorGeometry};

use super::tally::tally_item_results;
use super::{BoardHandle, WriteCoilsResult};
use crate::commit::Commit;
use crate::errors::KiCadError;
use crate::writer::{
    coils_to_board_items, io_elements_to_board_items, sensor_geometry_to_board_items,
};

impl<'a> BoardHandle<'a> {
    /// Write coils to the board atomically.
    ///
    /// Converts the coil geometry to KiCad board items via
    /// [`coils_to_board_items`], then opens a [`Commit`], creates the items,
    /// and ends the commit so all items appear as a single Ctrl+Z undo step.
    ///
    /// Returns a [`WriteCoilsResult`] with the per-item creation counts. The
    /// overall request may succeed (IRS_OK) even if KiCad rejected some
    /// individual items — those rejections are surfaced in `failures` rather
    /// than being turned into an `Err`, since the user can see them in the
    /// UI and a partial write is still useful diagnostic information.
    ///
    /// ## Logging
    /// Diagnostic lines are emitted to **stderr** via `eprintln!` so they
    /// surface in the Tauri dev console and the OS console. The lines are
    /// tagged with the prefix `[pcbmotorgen::write_coils]` and include the
    /// coil count, the per-layer breakdown, the items-attempted count, and
    /// the items-created count. This is the diagnostic channel the user
    /// needs to debug "0 of 0 written" issues — if you see
    /// `[pcbmotorgen::write_coils] coils=0` in the console, the bug is
    /// upstream (in coil generation), not in the KiCad IPC layer.
    ///
    /// ## Dry-run
    /// For a dry-run path that does NOT touch KiCad, see
    /// [`BoardHandle::write_coils_dry_run`]. The Tauri command layer
    /// dispatches to the dry-run method when the user passes
    /// `dry_run: true`, so the public signature of `write_coils` remains
    /// stable for callers that always want a real write.
    pub fn write_coils(
        &mut self,
        coils: &[PhaseCoil],
        num_layers: u32,
        rules: &DesignRules,
        active_area_length_mm: f64,
    ) -> Result<WriteCoilsResult, KiCadError> {
        self.write_coils_inner(
            coils,
            num_layers,
            rules,
            active_area_length_mm,
            /* dry_run = */ false,
        )
    }

    /// Dry-run path: convert the coil geometry to items and return a
    /// synthetic [`WriteCoilsResult`] reporting `items_attempted = items.len()`
    /// and `items_created = 0`. The KiCad commit / create flow is **not**
    /// executed, so no tracks land on the board.
    ///
    /// This is used by the UI's "preview" workflow so the user can see what
    /// *would* be written before clicking the real "Write" button. The
    /// [`crate::diagnostics::preview_coils`] function is the full-fidelity
    /// preview (with per-layer breakdown) — this method is the lightweight
    /// "I just want the item count" path that reuses the writer.
    pub fn write_coils_dry_run(
        &mut self,
        coils: &[PhaseCoil],
        num_layers: u32,
        rules: &DesignRules,
        active_area_length_mm: f64,
    ) -> Result<WriteCoilsResult, KiCadError> {
        self.write_coils_inner(
            coils,
            num_layers,
            rules,
            active_area_length_mm,
            /* dry_run = */ true,
        )
    }

    /// Atomically write induction-sensor tracks and vias. Sensor copper is
    /// authored for a two-layer board; terminal markers are never converted
    /// to pads or footprints.
    pub fn write_sensor_geometry(
        &mut self,
        geometry: &SensorGeometry,
        rules: &DesignRules,
        dry_run: bool,
    ) -> Result<WriteCoilsResult, KiCadError> {
        let items = sensor_geometry_to_board_items(geometry, rules);
        let items_attempted = items.len() as u32;
        if dry_run {
            return Ok(WriteCoilsResult {
                items_attempted,
                items_created: 0,
                failures: Vec::new(),
                failure_summary: Vec::new(),
            });
        }

        let mut commit = Commit::begin(self.client)?;
        let create_resp = commit.create_items(&items, &self.document)?;
        commit.end()?;
        let (items_created, failures, failure_summary) =
            tally_item_results(&create_resp.created_items);
        Ok(WriteCoilsResult {
            items_attempted,
            items_created,
            failures,
            failure_summary,
        })
    }

    /// Shared body for [`write_coils`](Self::write_coils) and
    /// [`write_coils_dry_run`](Self::write_coils_dry_run). The `dry_run`
    /// flag short-circuits before the commit/create IPC calls.
    fn write_coils_inner(
        &mut self,
        coils: &[PhaseCoil],
        num_layers: u32,
        rules: &DesignRules,
        active_area_length_mm: f64,
        dry_run: bool,
    ) -> Result<WriteCoilsResult, KiCadError> {
        let items = coils_to_board_items(coils, num_layers, rules, active_area_length_mm);
        let items_attempted = items.len() as u32;

        // --- Diagnostic logging -------------------------------------------
        // Per-layer breakdown so the user can see WHY coils are empty (or
        // not). Tagged with the writer name so it's easy to grep in the
        // Tauri dev console output.
        let mut per_layer: Vec<(u32, usize, usize)> = Vec::new(); // (layer, phases, segs)
        for layer_idx in 0..num_layers {
            let layer_coils: Vec<&PhaseCoil> =
                coils.iter().filter(|c| c.layer_idx == layer_idx).collect();
            let segs: usize = layer_coils.iter().map(|c| c.segments.len()).sum();
            if !layer_coils.is_empty() {
                per_layer.push((layer_idx, layer_coils.len(), segs));
            }
        }
        let board_name = self.name().unwrap_or_else(|_| "<unknown>".to_string());
        eprintln!(
            "[pcbmotorgen::write_coils] coils={} board={} num_layers={} \
             items_attempted={} dry_run={}",
            coils.len(),
            board_name,
            num_layers,
            items_attempted,
            dry_run,
        );
        if per_layer.is_empty() {
            eprintln!(
                "[pcbmotorgen::write_coils] WARNING: per_layer breakdown is empty — \
                 coil set produced 0 coils. Check num_layers / active_area_length_mm."
            );
        } else {
            for (l, n, s) in &per_layer {
                eprintln!("[pcbmotorgen::write_coils]   layer {l}: {n} phase(s), {s} segment(s)");
            }
        }

        if dry_run {
            // No commit, no socket round-trip. Return the preview.
            eprintln!(
                "[pcbmotorgen::write_coils] dry_run: returning preview with \
                 {items_attempted} item(s), 0 created (no board write performed)"
            );
            return Ok(WriteCoilsResult {
                items_attempted,
                items_created: 0,
                failures: Vec::new(),
                // Dry-run never round-trips with KiCad, so there are no
                // rejection codes to summarise. The UI's preview path
                // does not consult this field.
                failure_summary: Vec::new(),
            });
        }

        let mut commit = Commit::begin(self.client)?;
        let create_resp = commit.create_items(&items, &self.document)?;
        commit.end()?;

        // Tally per-item outcomes (pure helper in `super::tally`): count
        // the `ISC_OK` accepts, surface the first MAX_FAILURES_TO_REPORT
        // rejection messages verbatim, and build the code-grouped
        // `failure_summary` from ALL per-item outcomes.
        let (items_created, failures, failure_summary) =
            tally_item_results(&create_resp.created_items);

        eprintln!(
            "[pcbmotorgen::write_coils] done: items_attempted={} items_created={} \
             failures={} failure_codes={:?}",
            items_attempted,
            items_created,
            failures.len(),
            failure_summary,
        );

        Ok(WriteCoilsResult {
            items_attempted,
            items_created,
            failures,
            failure_summary,
        })
    }

    /// Write the IO elements of a [`RoutingResult`] (connector/IC pads +
    /// terminal fanout traces) to the board atomically — the additive
    /// counterpart of [`write_coils`](Self::write_coils).
    ///
    /// Items are produced by [`io_elements_to_board_items`]: one
    /// `FootprintInstance` per IO pad and one `Track` per IO fanout trace,
    /// all inside a single [`Commit`] (one Ctrl+Z undo step). A result
    /// without IO elements attempts zero items and succeeds trivially.
    pub fn write_io_elements(
        &mut self,
        result: &RoutingResult,
        num_layers: u32,
        rules: &DesignRules,
        active_area_length_mm: f64,
    ) -> Result<WriteCoilsResult, KiCadError> {
        self.write_io_inner(
            result,
            num_layers,
            rules,
            active_area_length_mm,
            /* dry_run = */ false,
        )
    }

    /// Dry-run path for [`write_io_elements`](Self::write_io_elements):
    /// converts the IO elements to items and returns a synthetic
    /// [`WriteCoilsResult`] with `items_created = 0`, without touching KiCad.
    pub fn write_io_elements_dry_run(
        &mut self,
        result: &RoutingResult,
        num_layers: u32,
        rules: &DesignRules,
        active_area_length_mm: f64,
    ) -> Result<WriteCoilsResult, KiCadError> {
        self.write_io_inner(
            result,
            num_layers,
            rules,
            active_area_length_mm,
            /* dry_run = */ true,
        )
    }

    /// Shared body for [`write_io_elements`](Self::write_io_elements) and
    /// [`write_io_elements_dry_run`](Self::write_io_elements_dry_run).
    fn write_io_inner(
        &mut self,
        result: &RoutingResult,
        num_layers: u32,
        rules: &DesignRules,
        active_area_length_mm: f64,
        dry_run: bool,
    ) -> Result<WriteCoilsResult, KiCadError> {
        let items = io_elements_to_board_items(result, num_layers, rules, active_area_length_mm);
        let items_attempted = items.len() as u32;

        let board_name = self.name().unwrap_or_else(|_| "<unknown>".to_string());
        eprintln!(
            "[pcbmotorgen::write_io_elements] io_pads={} io_traces={} board={} \
             num_layers={} items_attempted={} dry_run={}",
            result.io_pads.len(),
            result.io_traces.len(),
            board_name,
            num_layers,
            items_attempted,
            dry_run,
        );

        if dry_run || items.is_empty() {
            // No commit, no socket round-trip. (An empty IO set also skips
            // the IPC traffic — `Commit::begin` + `create_items(&[])` would
            // be a no-op round trip at best.)
            return Ok(WriteCoilsResult {
                items_attempted,
                items_created: 0,
                failures: Vec::new(),
                failure_summary: Vec::new(),
            });
        }

        let mut commit = Commit::begin(self.client)?;
        let create_resp = commit.create_items(&items, &self.document)?;
        commit.end()?;

        let (items_created, failures, failure_summary) =
            tally_item_results(&create_resp.created_items);

        eprintln!(
            "[pcbmotorgen::write_io_elements] done: items_attempted={} items_created={} \
             failures={} failure_codes={:?}",
            items_attempted,
            items_created,
            failures.len(),
            failure_summary,
        );

        Ok(WriteCoilsResult {
            items_attempted,
            items_created,
            failures,
            failure_summary,
        })
    }
}
