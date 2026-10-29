//! Native move demand from the exact active design, with bounded ownership.

use crate::ipc::LinearMotorConfigIpc;
use pcbmotorgen_export::cad_dxf::{CadGeometry, TerminalConnection};
use pcbmotorgen_simulation::drive::{move_power::routed::*, DriveSettings};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};

struct RunningMove {
    id: String,
    cancelled: Arc<AtomicBool>,
}
static RUNNING: Mutex<Option<RunningMove>> = Mutex::new(None);

struct MovePermit {
    id: String,
    cancelled: Arc<AtomicBool>,
}
impl MovePermit {
    fn acquire(id: String) -> Result<Self, String> {
        if id.trim().is_empty() || id.len() > 128 {
            return Err("Move request identity must contain 1..128 bytes".into());
        }
        let mut slot = RUNNING.lock().map_err(|_| "Move ownership lock failed")?;
        if slot.is_some() {
            return Err(
                "A move calculation is still running; wait for its completion or cancellation"
                    .into(),
            );
        }
        let cancelled = Arc::new(AtomicBool::new(false));
        *slot = Some(RunningMove {
            id: id.clone(),
            cancelled: cancelled.clone(),
        });
        Ok(Self { id, cancelled })
    }
    fn cancelled(&self) -> bool {
        self.cancelled.load(Ordering::Acquire)
    }
}
impl Drop for MovePermit {
    fn drop(&mut self) {
        if let Ok(mut slot) = RUNNING.lock() {
            if slot
                .as_ref()
                .is_some_and(|r| r.id == self.id && Arc::ptr_eq(&r.cancelled, &self.cancelled))
            {
                *slot = None;
            }
        }
    }
}

#[derive(Debug, Serialize)]
pub struct NativeMoveResult {
    pub request_id: String,
    pub input_sha256: String,
    /// Complete inputs, including imported copper, terminal picks and depths.
    pub inputs: serde_json::Value,
    pub provenance: String,
    pub result: RoutedMoveResult,
}

fn validate_star(config: &LinearMotorConfigIpc, cad: Option<&CadGeometry>) -> Result<(), String> {
    if let Some(cad) = cad {
        if cad.terminal_connection == Some(TerminalConnection::Delta) {
            return Err(
                "Delta move analysis is not supported; imported copper was not regenerated".into(),
            );
        }
        // Legacy files may have no declaration but explicit terminal picks at
        // one physical neutral point. Do not infer topology from the filename
        // or from unrelated generated-routing settings in an imported design.
        if cad.terminal_connection != Some(TerminalConnection::Star) {
            let grouped = cad.terminals_by_phase();
            let outputs: Vec<_> = grouped.values().flatten().map(|p| &p.output).collect();
            let shared = grouped.len() == 3
                && outputs.len() >= 3
                && outputs.iter().all(|p| {
                    p.layer == outputs[0].layer
                        && (p.position.x - outputs[0].position.x).abs() <= 1e-6
                        && (p.position.y - outputs[0].position.y).abs() <= 1e-6
                });
            if !shared {
                return Err("Imported winding connection is unknown: declare star or select a shared physical neutral in the existing copper".into());
            }
        }
    } else if config.routing_pattern != "infinity-braid"
        || config.routing_params.get("connection").copied() != Some(2.0)
    {
        return Err("Generated move analysis requires an explicitly declared star winding; closed/delta/unknown connections are unsupported".into());
    }
    Ok(())
}

fn calculate(
    config: LinearMotorConfigIpc,
    drive: DriveSettings,
    request: RoutedMoveRequest,
    cad_geometry: Option<CadGeometry>,
    permit: &MovePermit,
) -> Result<NativeMoveResult, String> {
    if permit.cancelled() {
        return Err("Move power calculation cancelled".into());
    }
    validate_star(&config, cad_geometry.as_ref())?;
    let core = config.to_core();
    core.validate().map_err(|e| e.to_string())?;
    let (routing, sim, hints) = if let Some(cad) = &cad_geometry {
        let board = super::cad_source::CadBoard::new(cad, &core)?;
        let sim = board.simulation_input(cad, &core);
        (
            board.routing,
            sim,
            super::cad_source::CadBoard::drive_hints(cad),
        )
    } else {
        core.design_rules().validate_trace_width()?;
        let routing = pcbmotorgen_routing::generate_routing_result(
            &core.routing_context(),
            &core.routing_pattern_id(),
        )
        .map_err(|e| e.to_string())?;
        (routing, core.to_simulation(), Default::default())
    };
    let inputs = serde_json::json!({ "topology": "linear", "config": config, "drive": drive,
        "cad_geometry": cad_geometry, "move_request": request });
    let input_sha256 = format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&inputs).map_err(|e| e.to_string())?)
    );
    let result = evaluate_routed_move(
        &sim,
        &routing,
        &drive,
        &hints,
        &request,
        config.meshing as usize,
        &|| permit.cancelled(),
    )?;
    if permit.cancelled() {
        return Err("Move power calculation cancelled; result withheld".into());
    }
    Ok(NativeMoveResult {
        request_id: permit.id.clone(),
        input_sha256,
        inputs,
        provenance: "simulated_not_measured".into(),
        result,
    })
}

#[tauri::command]
pub async fn evaluate_move_power(
    request_id: String,
    inputs: serde_json::Value,
) -> Result<NativeMoveResult, String> {
    if inputs.get("topology").and_then(serde_json::Value::as_str) != Some("linear") {
        return Err(
            "Move power requires an explicit linear topology; rotary motion is not supported"
                .into(),
        );
    }
    #[derive(Deserialize)]
    struct Inputs {
        config: LinearMotorConfigIpc,
        drive: DriveSettings,
        move_request: RoutedMoveRequest,
        cad_geometry: Option<CadGeometry>,
    }
    let typed: Inputs =
        serde_json::from_value(inputs.clone()).map_err(|e| format!("Invalid move inputs: {e}"))?;
    let permit = MovePermit::acquire(request_id)?;
    tauri::async_runtime::spawn_blocking(move || {
        let mut result = calculate(
            typed.config,
            typed.drive,
            typed.move_request,
            typed.cad_geometry,
            &permit,
        )?;
        // Bind publication to the exact received payload, not a DTO roundtrip
        // which can omit optional empty fields or add legacy defaults.
        result.input_sha256 = format!(
            "{:x}",
            Sha256::digest(serde_json::to_vec(&inputs).map_err(|e| e.to_string())?)
        );
        result.inputs = inputs;
        if permit.cancelled() {
            return Err("Move power calculation cancelled; result withheld".into());
        }
        Ok(result)
    })
    .await
    .map_err(|e| format!("Move power worker failed: {e}"))?
}

/// Cooperative cancellation. The worker retains ownership until its next
/// cancellation checkpoint, including after any noninterruptible field/L stage.
#[tauri::command]
pub fn cancel_move_power(request_id: String) -> Result<bool, String> {
    let slot = RUNNING.lock().map_err(|_| "Move ownership lock failed")?;
    if let Some(running) = slot.as_ref().filter(|r| r.id == request_id) {
        running.cancelled.store(true, Ordering::Release);
        return Ok(true);
    }
    Ok(false)
}

#[cfg(test)]
mod tests;
