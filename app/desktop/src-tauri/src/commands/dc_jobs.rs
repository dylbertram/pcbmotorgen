//! Opt-in experimental DC worker. No arbitrary executable or input geometry
//! snapshot is accepted from IPC. Actual copper is rebuilt by the host.
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File},
    io::Write,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    time::{Duration, Instant},
};

const TIMEOUT: Duration = Duration::from_secs(360);
/// Written only by the offline registration of a case whose whole force-matrix
/// audit passed. The worker re-verifies every entry; the host only lists them.
const REGISTRY: &str = "dc-qualified-linear-cases-v1.json";

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DcStudy {
    pub request_id: String,
    pub material_model: Value,
    pub return_geometry: Value,
    pub current_a: f64,
    pub pm_offset_x_m: f64,
    pub placement_acknowledged: bool,
}

impl DcStudy {
    fn validate(&self) -> Result<(), String> {
        if self.request_id.is_empty()
            || self.request_id.len() > 128
            || !self
                .request_id
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || b"-_".contains(&c))
        {
            return Err("Use a unique alphanumeric DC request ID, at most 128 characters".into());
        }
        if !self.placement_acknowledged {
            return Err("Explicit physical material placement acknowledgement required; no automatic stack move".into());
        }
        if ![0., 0.1, -0.1, 0.5, -0.5].contains(&self.current_a)
            || ![0., 0.0001, -0.0001].contains(&self.pm_offset_x_m)
        {
            return Err("DC coupling currently admits only the recorded sampled currents and PM poses; no interpolation".into());
        }
        if !self.material_model.is_object() || !self.return_geometry.is_object() {
            return Err("Explicit physical material and finite return geometry required".into());
        }
        Ok(())
    }

    fn request(&self, winding: Value) -> Value {
        // v2 names no source basis: the worker must find exactly one registered,
        // re-verified qualified case matching this rebuilt copper and placement.
        json!({"schema":"finite-dc-live-request-v2", "request_id":self.request_id,
            "winding":winding, "material_model":self.material_model, "return_geometry":self.return_geometry,
            "current_a":self.current_a,
            "pm_offset_x_m":self.pm_offset_x_m, "placement_acknowledged":self.placement_acknowledged})
    }
}

#[derive(Clone)]
struct Runtime {
    python: PathBuf,
    script: PathBuf,
    archive: PathBuf,
}

impl Runtime {
    fn from_env() -> Result<Self, String> {
        if !cfg!(unix) {
            return Err("Managed DC jobs are currently qualified only on POSIX hosts".into());
        }
        let configured = |key: &str| -> Result<PathBuf, String> {
            let path = std::env::var_os(key).ok_or_else(|| {
                format!("DC worker is disabled: configure {key} on the desktop host")
            })?;
            let path = PathBuf::from(path);
            if !path.is_absolute() {
                return Err(format!("{key} must be an absolute host path"));
            }
            path.canonicalize()
                .map_err(|error| format!("{key}: {error}"))
        };
        // Keep the virtualenv executable path, not its resolved symlink target:
        // resolving python to the base interpreter drops its installed packages.
        let python_path = std::env::var_os("PCB_MOTOR_DC_PYTHON")
            .ok_or("DC worker is disabled: configure PCB_MOTOR_DC_PYTHON on the desktop host")?;
        let python = PathBuf::from(python_path);
        if !python.is_absolute() || !python.is_file() {
            return Err(
                "PCB_MOTOR_DC_PYTHON must name an absolute installed Python executable".into(),
            );
        }
        let root = configured("PCB_MOTOR_DC_SOLVER_ROOT")?;
        let archive = configured("PCB_MOTOR_DC_ARCHIVE_ROOT")?;
        let script = root.join("desktop_dc_job.py");
        if !script.is_file() || !archive.is_dir() {
            return Err("DC solver installation/evidence root is missing".into());
        }
        Ok(Self {
            python,
            script,
            archive,
        })
    }

    fn command(&self, request: &Path, job: &Path) -> Command {
        let mut command = Command::new(&self.python);
        command
            .arg(&self.script)
            .arg("--request")
            .arg(request)
            .arg("--archive-root")
            .arg(&self.archive)
            .arg("--job")
            .arg(job)
            .current_dir(job)
            .env("PCB_MOTOR_SOLVER_TIMEOUT", "350")
            .env("OPENBLAS_NUM_THREADS", "1")
            .env("OMP_NUM_THREADS", "1")
            .env("VECLIB_MAXIMUM_THREADS", "1")
            .env_remove("PCB_MOTOR_COMMAND_RECEIPT")
            .stdin(Stdio::null());
        command
    }
}

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct DcJobStatus {
    pub request_id: String,
    pub job_id: String,
    pub state: String,
    pub elapsed_seconds: f64,
    pub evidence_directory: String,
    pub request_sha256: String,
    pub error: Option<String>,
    pub result: Option<Value>,
}

impl DcJobStatus {
    fn active(&self) -> bool {
        matches!(self.state.as_str(), "running" | "cancelling")
    }
}

struct Job {
    status: DcJobStatus,
    cancel: Arc<AtomicBool>,
}

/// A dropped monitor closure must not leave its worker running, including
/// thread-spawn failures and unexpected unwinding. Never signal a reaped PID.
struct OwnedChild {
    process: std::process::Child,
    reaped: bool,
}
impl OwnedChild {
    fn try_wait(&mut self) -> std::io::Result<Option<std::process::ExitStatus>> {
        let status = self.process.try_wait()?;
        if status.is_some() {
            self.reaped = true;
        }
        Ok(status)
    }
    fn stop(&mut self) {
        if self.reaped {
            return;
        }
        #[cfg(unix)]
        unsafe {
            libc::kill(-(self.process.id() as i32), libc::SIGKILL);
        }
        let _ = self.process.kill();
        let _ = self.process.wait();
        self.reaped = true;
    }
}
impl Drop for OwnedChild {
    fn drop(&mut self) {
        self.stop();
    }
}

#[derive(Default, Clone)]
pub struct DcJobs {
    job: Arc<Mutex<Option<Job>>>,
    shutting_down: Arc<AtomicBool>,
    inspecting: Arc<AtomicBool>,
}

struct InspectionPermit(Arc<AtomicBool>);
impl Drop for InspectionPermit {
    fn drop(&mut self) { self.0.store(false, Ordering::SeqCst); }
}

fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn read_json(path: &Path) -> Result<Value, String> {
    if fs::metadata(path).map_err(|error| error.to_string())?.len() > 8_000_000 {
        return Err("DC report exceeds the declared 8 MB result cap".into());
    }
    serde_json::from_slice(&fs::read(path).map_err(|error| error.to_string())?)
        .map_err(|error| error.to_string())
}

fn verify_result(job: &Path, request: &Value, request_sha: &str) -> Result<Value, String> {
    if hash(&fs::read(job.join("request.json")).map_err(|error| error.to_string())?) != request_sha
    {
        return Err("DC request changed during solve; stale result suppressed".into());
    }
    let receipt = read_json(&job.join("desktop-worker.log.command.json"))?;
    if receipt["status"] != "completed" || receipt["exit_code"] != 0 {
        return Err("DC worker has no successful supervisor receipt".into());
    }
    let result = read_json(&job.join("result/summary.json"))?;
    if result["status"] != "passed-fresh-qualified-geometry-dc-request-only"
        || !result["qualified_case"]["case_id"].is_string()
        || result["qualified_case"] != result["eligibility"]["qualified_case"]
        || result["input_request_sha256"] != request_sha
        || result["eligibility"]["request_id"] != request["request_id"]
        || result["eligibility"]["current_a"] != request["current_a"]
        || result["eligibility"]["pm_offset_x_m"] != request["pm_offset_x_m"]
    {
        return Err("DC worker returned an unverified or mismatched request result".into());
    }
    let force = result["pm_array_force_n"]
        .as_array()
        .ok_or("DC force vector is missing")?;
    if force.len() != 3
        || force
            .iter()
            .any(|value| value.as_f64().map_or(true, |x| !x.is_finite()))
    {
        return Err("DC force vector is nonfinite or malformed".into());
    }
    let child = job.join("result/fresh-magnetic-solve/summary.json");
    if hash(&fs::read(&child).map_err(|error| error.to_string())?)
        != result["fresh_solve_summary_sha256"]
    {
        return Err("Fresh DC magnetic report hash changed".into());
    }
    let child = read_json(&child)?;
    if child["status"] != "passed-recorded-finite-current-static-pilot-only"
        || child["failures"] != json!([])
    {
        return Err("Fresh DC numerical controls did not pass".into());
    }
    let states = child["states"]
        .as_object()
        .ok_or("Fresh DC states are missing")?;
    let current = request["current_a"]
        .as_f64()
        .ok_or("Missing requested current")?;
    let selected = states
        .iter()
        .find(|(key, _)| key.parse::<f64>().ok() == Some(current))
        .map(|(_, state)| state)
        .ok_or("Requested current is absent from fresh solve")?;
    if selected["pm_array_force_n"] != result["pm_array_force_n"]
        || selected["solution_sha256"] != result["fresh_solution_sha256"]
        || result["fresh_solution"]
            != format!(
                "fresh-magnetic-solve/{}",
                selected["solution"].as_str().ok_or("Missing solution")?
            )
    {
        return Err("DC result does not match the requested freshly solved state".into());
    }
    let solution = result["fresh_solution"]
        .as_str()
        .ok_or("Fresh DC solution is missing")?;
    let relative = Path::new(solution);
    if relative
        .components()
        .any(|component| !matches!(component, std::path::Component::Normal(_)))
    {
        return Err("Invalid fresh solution path".into());
    }
    let base = job
        .join("result")
        .canonicalize()
        .map_err(|error| error.to_string())?;
    let solution = base
        .join(relative)
        .canonicalize()
        .map_err(|error| error.to_string())?;
    if !solution.starts_with(&base)
        || hash(&fs::read(solution).map_err(|error| error.to_string())?)
            != result["fresh_solution_sha256"]
    {
        return Err("Fresh DC solution hash/identity check failed".into());
    }
    Ok(result)
}

impl DcJobs {
    fn begin_inspection(&self) -> Result<InspectionPermit, String> {
        let slot = self.job.lock().map_err(|_| "DC job state failed; restart the app")?;
        if self.shutting_down.load(Ordering::SeqCst) {
            return Err("DC worker is shutting down".into());
        }
        if slot.as_ref().is_some_and(|job| job.status.active()) {
            return Err("Wait for the DC job to finish or cancel before checking another design".into());
        }
        self.inspecting.compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .map_err(|_| "A DC applicability check is already running")?;
        Ok(InspectionPermit(self.inspecting.clone()))
    }

    fn launch(
        &self,
        runtime: Runtime,
        request: Value,
        timeout: Duration,
    ) -> Result<DcJobStatus, String> {
        let bytes = serde_json::to_vec_pretty(&request).map_err(|error| error.to_string())?;
        if bytes.len() > 8_000_000 {
            return Err("DC request exceeds the declared 8 MB input cap".into());
        }
        let mut slot = self
            .job
            .lock()
            .map_err(|_| "DC job state failed; restart the app")?;
        if self.shutting_down.load(Ordering::SeqCst) {
            return Err("DC worker is shutting down; no new job was launched".into());
        }
        if self.inspecting.load(Ordering::SeqCst) {
            return Err("Wait for the DC applicability check before starting a numerical job".into());
        }
        if let Some(previous) = slot.as_ref() {
            if previous.status.active() {
                return Err("A DC job is already running or cancelling".into());
            }
            if previous.status.request_id == request["request_id"].as_str().unwrap_or("") {
                return Err("Use a new request ID before retrying a DC job".into());
            }
        }
        let output = runtime.archive.join("dc-desktop-jobs");
        fs::create_dir_all(&output).map_err(|error| error.to_string())?;
        let job = tempfile::Builder::new()
            .prefix("dc-")
            .tempdir_in(output)
            .map_err(|error| error.to_string())?
            .keep();
        let request_path = job.join("request.json");
        File::options()
            .write(true)
            .create_new(true)
            .open(&request_path)
            .and_then(|mut file| file.write_all(&bytes))
            .map_err(|error| error.to_string())?;
        let job_id = job.file_name().unwrap().to_string_lossy().to_string();
        let cancel = Arc::new(AtomicBool::new(false));
        let initial = DcJobStatus {
            request_id: request["request_id"]
                .as_str()
                .ok_or("Missing request ID")?
                .into(),
            job_id: job_id.clone(),
            state: "running".into(),
            elapsed_seconds: 0.,
            evidence_directory: job.to_string_lossy().into(),
            request_sha256: hash(&bytes),
            error: None,
            result: None,
        };
        let mut command = runtime.command(&request_path, &job);
        let log = File::options()
            .write(true)
            .create_new(true)
            .open(job.join("desktop.log"))
            .map_err(|error| error.to_string())?;
        command
            .stdout(log.try_clone().map_err(|error| error.to_string())?)
            .stderr(log);
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            command.process_group(0);
        }
        let mut child = OwnedChild {
            process: command
                .spawn()
                .map_err(|error| format!("DC worker could not start: {error}"))?,
            reaped: false,
        };
        fs::write(job.join("desktop-launch.json"), serde_json::to_vec_pretty(&json!({
            "request_sha256":initial.request_sha256,"pid":child.process.id(),"cleanup_scope":"owned-posix-process-group",
            "timeout_seconds":timeout.as_secs_f64(),"python":runtime.python,"worker":runtime.script,
            "worker_sha256":hash(&fs::read(&runtime.script).map_err(|error| error.to_string())?),
            "archive":runtime.archive,"host_version":env!("CARGO_PKG_VERSION")
        })).unwrap()).map_err(|error| error.to_string())?;
        let shared = self.clone();
        let initial_thread = initial.clone();
        let cancel_thread = cancel.clone();
        *slot = Some(Job {
            status: initial.clone(),
            cancel,
        });
        let job_on_spawn_failure = job.clone();
        let spawned = std::thread::Builder::new()
            .name("dc-job-supervisor".into())
            .spawn(move || {
                let start = Instant::now();
                let mut final_status = initial_thread;
                let request_sha = final_status.request_sha256.clone();
                let mut finish = |state: &str, error: Option<String>, result: Option<Value>| {
                    final_status.state = state.into();
                    final_status.error = error;
                    final_status.result = result;
                    final_status.elapsed_seconds = start.elapsed().as_secs_f64();
                    if let Ok(mut slot) = shared.job.lock() {
                        if slot
                            .as_ref()
                            .is_some_and(|entry| entry.status.job_id == job_id)
                        {
                            // Serialize cancellation with result publication. A cancel
                            // accepted while verification ran must suppress its force.
                            if cancel_thread.load(Ordering::SeqCst) {
                                final_status.state = "cancelled".into();
                                final_status.result = None;
                                final_status.error =
                                    Some("DC job cancelled; no force returned".into());
                            }
                            let _ = fs::write(
                                job.join("desktop-status.json"),
                                serde_json::to_vec_pretty(&final_status).unwrap(),
                            );
                            *slot = Some(Job {
                                status: final_status.clone(),
                                cancel: cancel_thread.clone(),
                            });
                        }
                    }
                };
                loop {
                    // Signal only while the owned child has not been reaped. Its PID
                    // cannot be reused before wait, even if it already exited.
                    if cancel_thread.load(Ordering::SeqCst) || start.elapsed() >= timeout {
                        let cancelled = cancel_thread.load(Ordering::SeqCst);
                        child.stop();
                        finish(
                            if cancelled { "cancelled" } else { "timed_out" },
                            Some(if cancelled {
                                "DC job cancelled; no force returned".into()
                            } else {
                                "DC whole-job timeout; no force returned".into()
                            }),
                            None,
                        );
                        return;
                    }
                    match child.try_wait() {
                        Ok(Some(exit)) => {
                            if cancel_thread.load(Ordering::SeqCst) {
                                finish(
                                    "cancelled",
                                    Some("DC job cancelled; no force returned".into()),
                                    None,
                                );
                            } else if exit.success() {
                                match verify_result(&job, &request, &request_sha) {
                                    Ok(result) => finish("completed", None, Some(result)),
                                    Err(error) => finish("failed", Some(error), None),
                                }
                            } else {
                                let detail = fs::read_to_string(job.join("desktop-worker.log"))
                                    .unwrap_or_default();
                                let tail: String = detail
                                    .chars()
                                    .rev()
                                    .take(2000)
                                    .collect::<String>()
                                    .chars()
                                    .rev()
                                    .collect();
                                finish(
                                    "failed",
                                    Some(format!(
                                        "DC worker failed ({exit}); no force returned. {tail}"
                                    )),
                                    None,
                                );
                            }
                            return;
                        }
                        Err(error) => {
                            child.stop();
                            finish(
                                "failed",
                                Some(format!("DC worker supervision failed: {error}")),
                                None,
                            );
                            return;
                        }
                        Ok(None) => std::thread::sleep(Duration::from_millis(50)),
                    }
                }
            });
        if let Err(error) = spawned {
            // The rejected closure drops OwnedChild and cleans its group.
            let mut failed = initial.clone();
            failed.state = "failed".into();
            failed.error = Some(format!("DC supervisor thread failed: {error}"));
            let _ = fs::write(
                job_on_spawn_failure.join("desktop-status.json"),
                serde_json::to_vec_pretty(&failed).unwrap(),
            );
            if let Some(job) = slot.as_mut() {
                job.status = failed;
            }
            return Err(format!("DC supervisor thread failed: {error}"));
        }
        Ok(initial)
    }

    pub fn status(&self, id: &str) -> Result<DcJobStatus, String> {
        let slot = self.job.lock().map_err(|_| "DC job state failed")?;
        let job = slot
            .as_ref()
            .filter(|job| job.status.job_id == id)
            .ok_or("Unknown or superseded DC job")?;
        Ok(job.status.clone())
    }

    pub fn cancel(&self, id: &str) -> Result<DcJobStatus, String> {
        let mut slot = self.job.lock().map_err(|_| "DC job state failed")?;
        let job = slot
            .as_mut()
            .filter(|job| job.status.job_id == id)
            .ok_or("Unknown or superseded DC job")?;
        if job.status.active() {
            job.cancel.store(true, Ordering::SeqCst);
            job.status.state = "cancelling".into();
            job.status.result = None;
        }
        Ok(job.status.clone())
    }

    pub fn shutdown(&self) {
        // Geometry preparation is asynchronous. A late start must not launch a
        // new child after the app's exit cleanup has already run.
        self.shutting_down.store(true, Ordering::SeqCst);
        let id = self
            .job
            .lock()
            .ok()
            .and_then(|slot| slot.as_ref().map(|job| job.status.job_id.clone()));
        if let Some(id) = id {
            let _ = self.cancel(&id);
            for _ in 0..100 {
                if self.status(&id).map_or(true, |status| !status.active()) {
                    break;
                }
                std::thread::sleep(Duration::from_millis(20));
            }
        }
        for _ in 0..100 {
            if !self.inspecting.load(Ordering::SeqCst) { break; }
            std::thread::sleep(Duration::from_millis(20));
        }
    }
}

/// Registered qualified cases with their audited placement/return, for display
/// and explicit acknowledgement only. Admission is decided by the worker.
fn qualified_cases(archive: &Path) -> Result<Vec<Value>, String> {
    let path = archive.join(REGISTRY);
    if !path.exists() {
        return Ok(vec![]);
    }
    let registry = read_json(&path)?;
    if registry["schema"] != "dc-qualified-linear-cases-v1" {
        return Err("Unrecognized qualified-case registry".into());
    }
    Ok(registry["cases"]
        .as_array()
        .ok_or("Malformed qualified-case registry")?
        .iter()
        .filter(|case| case["case_id"].is_string() && case["declaration"].is_object())
        .map(|case| json!({"case_id":case["case_id"],"label":case["label"],"audit_sha256":case["audit_sha256"],
            "declaration":case["declaration"]}))
        .collect())
}

fn verify_applicability(value: Value, request: &Value, request_sha: &str) -> Result<Value, String> {
    let fields = ["schema", "request_id", "request_sha256", "state", "source_status", "force_status", "reason", "qualified_case"];
    let object = value.as_object().ok_or("Malformed DC applicability report")?;
    if object.len() != fields.len() || object.keys().any(|key| !fields.contains(&key.as_str()))
        || value["schema"] != "finite-dc-applicability-v1"
        || value["request_id"] != request["request_id"] || value["request_sha256"] != request_sha
        || !value["reason"].is_string()
    {
        return Err("Unverified or stale DC applicability report".into());
    }
    if value["state"] == "qualified" {
        if value["source_status"] != "qualified-exact-basis" || value["force_status"] != "qualified-sampled-states"
            || !value["qualified_case"]["case_id"].is_string() || !value["qualified_case"]["audit_sha256"].is_string()
        {
            return Err("Missing exact-case qualification in applicability report".into());
        }
    } else if !["preparation-required", "unsupported"].iter().any(|state| value["state"] == *state)
        || value["source_status"] != "unqualified" || value["force_status"] != "unqualified" || !value["qualified_case"].is_null()
    {
        return Err("Invalid unqualified applicability state".into());
    }
    Ok(value)
}

fn inspect_actual_request(runtime: Runtime, request: Value, shutting_down: Arc<AtomicBool>) -> Result<Value, String> {
    if shutting_down.load(Ordering::SeqCst) { return Err("DC worker is shutting down; no inspection launched".into()); }
    let script = runtime.script.with_file_name("dc_applicability.py");
    if !script.is_file() { return Err("DC applicability checker is missing from the installed worker".into()); }
    let bytes = serde_json::to_vec_pretty(&request).map_err(|error| error.to_string())?;
    if bytes.len() > 8_000_000 { return Err("DC request exceeds the 8 MB input cap".into()); }
    let root = runtime.archive.join("dc-desktop-inspections");
    fs::create_dir_all(&root).map_err(|error| error.to_string())?;
    let directory = tempfile::Builder::new().prefix("inspect-").tempdir_in(root).map_err(|error| error.to_string())?.keep();
    let request_path = directory.join("request.json");
    fs::write(&request_path, &bytes).map_err(|error| error.to_string())?;
    let output = File::create(directory.join("applicability.json")).map_err(|error| error.to_string())?;
    let errors = File::create(directory.join("inspection.log")).map_err(|error| error.to_string())?;
    let mut command = Command::new(&runtime.python);
    command.arg(script).arg("--request").arg(&request_path).arg("--archive-root").arg(&runtime.archive)
        .env("OPENBLAS_NUM_THREADS", "1").env("OMP_NUM_THREADS", "1").env("VECLIB_MAXIMUM_THREADS", "1")
        .stdin(Stdio::null()).stdout(output).stderr(errors);
    #[cfg(unix)]
    { use std::os::unix::process::CommandExt; command.process_group(0); }
    let mut child = OwnedChild { process: command.spawn().map_err(|error| error.to_string())?, reaped: false };
    let start = Instant::now();
    loop {
        if shutting_down.load(Ordering::SeqCst) {
            child.stop(); return Err("DC applicability check stopped during app shutdown".into());
        }
        if start.elapsed() >= Duration::from_secs(30) {
            child.stop(); return Err("DC applicability check exceeded its 30 s budget; no force was calculated".into());
        }
        match child.try_wait().map_err(|error| error.to_string())? {
            Some(exit) if exit.success() => break,
            Some(_) => return Err(format!("DC applicability check failed; no force was calculated. See {}", directory.join("inspection.log").display())),
            None => std::thread::sleep(Duration::from_millis(25)),
        }
    }
    let digest = hash(&bytes);
    if hash(&fs::read(&request_path).map_err(|error| error.to_string())?) != digest {
        return Err("DC inspection input changed; stale applicability suppressed".into());
    }
    verify_applicability(read_json(&directory.join("applicability.json"))?, &request, &digest)
}

#[tauri::command]
pub async fn inspect_dc_coupling(
    jobs: tauri::State<'_, DcJobs>,
    config: crate::ipc::LinearMotorConfigIpc,
    drive_settings: pcbmotorgen_simulation::drive::DriveSettings,
    cad_geometry: Option<pcbmotorgen_export::cad_dxf::CadGeometry>,
    study: DcStudy,
) -> Result<Value, String> {
    study.validate()?;
    let permit = jobs.begin_inspection()?;
    let shutting_down = jobs.shutting_down.clone();
    let runtime = Runtime::from_env()?;
    let winding = super::physics::prepare_dc_winding_geometry(config, drive_settings, cad_geometry).await?;
    tauri::async_runtime::spawn_blocking(move || {
        let _permit = permit;
        inspect_actual_request(runtime, study.request(winding), shutting_down)
    })
        .await.map_err(|error| error.to_string())?
}

#[tauri::command]
pub fn dc_coupling_capability() -> Value {
    match Runtime::from_env().and_then(|runtime| qualified_cases(&runtime.archive)) {
        Ok(cases) if cases.is_empty() => {
            json!({"available":false,"reason":"No qualified linear DC case is registered on this host; designs need offline qualification first"})
        }
        Ok(cases) => {
            json!({"available":true,"qualified_cases":cases,
                "scope":"Registered individually qualified linear designs and their sampled current/pose states only; provisional reversible material law; no interpolation or hardware qualification"})
        }
        Err(error) => json!({"available":false,"reason":error}),
    }
}

#[tauri::command]
pub async fn start_dc_coupling(
    jobs: tauri::State<'_, DcJobs>,
    config: crate::ipc::LinearMotorConfigIpc,
    drive_settings: pcbmotorgen_simulation::drive::DriveSettings,
    cad_geometry: Option<pcbmotorgen_export::cad_dxf::CadGeometry>,
    study: DcStudy,
) -> Result<DcJobStatus, String> {
    study.validate()?;
    let runtime = Runtime::from_env()?;
    let winding =
        super::physics::prepare_dc_winding_geometry(config, drive_settings, cad_geometry).await?;
    jobs.launch(runtime, study.request(winding), TIMEOUT)
}

#[tauri::command]
pub fn dc_coupling_status(
    jobs: tauri::State<'_, DcJobs>,
    job_id: String,
) -> Result<DcJobStatus, String> {
    jobs.status(&job_id)
}

#[tauri::command]
pub fn cancel_dc_coupling(
    jobs: tauri::State<'_, DcJobs>,
    job_id: String,
) -> Result<DcJobStatus, String> {
    jobs.cancel(&job_id)
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;

    fn runtime(directory: &Path, script: &str) -> Runtime {
        let path = directory.join("test-worker.py");
        fs::write(&path, script).unwrap();
        Runtime {
            python: PathBuf::from("/usr/bin/python3"),
            script: path,
            archive: directory.into(),
        }
    }

    fn wait(jobs: &DcJobs, id: &str) -> DcJobStatus {
        let start = Instant::now();
        loop {
            let status = jobs.status(id).unwrap();
            if !status.active() {
                return status;
            }
            assert!(
                start.elapsed() < Duration::from_secs(15),
                "job did not terminate"
            );
            std::thread::sleep(Duration::from_millis(20));
        }
    }

    #[test]
    fn cancelled_and_timed_out_jobs_kill_nested_process_and_never_return_force() {
        for cancel in [true, false] {
            let dir = tempfile::tempdir().unwrap();
            let rt = runtime(dir.path(), "import subprocess,sys,time\nfrom pathlib import Path\np=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\nPath('nested.pid').write_text(str(p.pid))\ntime.sleep(60)\n");
            let jobs = DcJobs::default();
            let initial = jobs
                .launch(
                    rt.clone(),
                    json!({"request_id":"test"}),
                    Duration::from_secs(2),
                )
                .unwrap();
            assert!(jobs
                .launch(rt, json!({"request_id":"concurrent"}), TIMEOUT)
                .is_err());
            let evidence = PathBuf::from(&initial.evidence_directory);
            let start = Instant::now();
            while !evidence.join("nested.pid").exists() {
                assert!(start.elapsed() < Duration::from_secs(1));
                std::thread::sleep(Duration::from_millis(10));
            }
            if cancel {
                assert_eq!(jobs.cancel(&initial.job_id).unwrap().state, "cancelling");
            }
            let status = wait(&jobs, &initial.job_id);
            assert_eq!(status.state, if cancel { "cancelled" } else { "timed_out" });
            assert!(status.result.is_none());
            let pid: i32 = fs::read_to_string(evidence.join("nested.pid"))
                .unwrap()
                .parse()
                .unwrap();
            // A killed child may briefly remain defunct until launchd/init reaps
            // it. ps must not show a live/sleeping numerical worker.
            let ps = Command::new("ps")
                .args(["-o", "stat=", "-p", &pid.to_string()])
                .output()
                .unwrap();
            let state = String::from_utf8_lossy(&ps.stdout);
            assert!(
                state.trim().is_empty() || state.trim().starts_with('Z'),
                "nested process survived: {state}"
            );
            assert!(evidence.join("request.json").exists());
            assert!(evidence.join("desktop-status.json").exists());
        }
    }

    #[test]
    fn failed_workers_and_unverified_success_cannot_publish_force() {
        for script in ["raise SystemExit(2)", "pass"] {
            let dir = tempfile::tempdir().unwrap();
            let jobs = DcJobs::default();
            let initial = jobs
                .launch(
                    runtime(dir.path(), script),
                    json!({"request_id":"failure"}),
                    TIMEOUT,
                )
                .unwrap();
            let status = wait(&jobs, &initial.job_id);
            assert_eq!(status.state, "failed");
            assert!(status.result.is_none());
            assert!(jobs.status("arbitrary-job-id").is_err());
            assert!(jobs.cancel("arbitrary-job-id").is_err());
        }
    }

    #[test]
    fn explicit_study_limits_and_unknown_inputs_are_rejected() {
        let valid = json!({"request_id":"bounded-1","material_model":{},"return_geometry":{},
            "current_a":0.1,"pm_offset_x_m":0.,"placement_acknowledged":true});
        let study: DcStudy = serde_json::from_value(valid.clone()).unwrap();
        study.validate().unwrap();
        for (key, value) in [
            ("request_id", json!("../../other")),
            ("placement_acknowledged", json!(false)),
            ("current_a", json!(0.2)),
            ("pm_offset_x_m", json!(0.00001)),
            ("return_geometry", json!(null)),
        ] {
            let mut changed = valid.clone();
            changed[key] = value;
            assert!(serde_json::from_value::<DcStudy>(changed)
                .unwrap()
                .validate()
                .is_err());
        }
        let mut changed = valid;
        changed["python"] = json!("/tmp/arbitrary");
        assert!(serde_json::from_value::<DcStudy>(changed).is_err());
    }

    #[test]
    fn result_verifier_rejects_stale_request_wrong_state_and_changed_evidence() {
        // Serialization/control-flow fixture only, not numerical evidence.
        let dir = tempfile::tempdir().unwrap();
        let job = dir.path();
        let request = json!({"request_id":"binding","current_a":0.1,"pm_offset_x_m":0.0});
        let bytes = serde_json::to_vec_pretty(&request).unwrap();
        let sha = hash(&bytes);
        fs::write(job.join("request.json"), &bytes).unwrap();
        fs::create_dir_all(job.join("result/fresh-magnetic-solve")).unwrap();
        fs::write(
            job.join("desktop-worker.log.command.json"),
            br#"{"status":"completed","exit_code":0}"#,
        )
        .unwrap();
        let solution = b"verifier serialization fixture, not a solver state";
        fs::write(job.join("result/fresh-magnetic-solve/state.sol"), solution).unwrap();
        let child = serde_json::to_vec(&json!({"status":"passed-recorded-finite-current-static-pilot-only","failures":[],
            "states":{"0.1":{"solution":"state.sol","solution_sha256":hash(solution),"pm_array_force_n":[1.,2.,3.]}}})).unwrap();
        fs::write(job.join("result/fresh-magnetic-solve/summary.json"), &child).unwrap();
        let case = json!({"case_id":"case","label":"fixture","audit_sha256":"audit"});
        let result = json!({"status":"passed-fresh-qualified-geometry-dc-request-only","input_request_sha256":sha,
            "qualified_case":case,
            "eligibility":{"request_id":"binding","current_a":0.1,"pm_offset_x_m":0.0,"qualified_case":case},"pm_array_force_n":[1.,2.,3.],
            "fresh_solution":"fresh-magnetic-solve/state.sol","fresh_solution_sha256":hash(solution),"fresh_solve_summary_sha256":hash(&child)});
        let save = |value: &Value| {
            fs::write(
                job.join("result/summary.json"),
                serde_json::to_vec(value).unwrap(),
            )
            .unwrap()
        };
        save(&result);
        assert!(verify_result(job, &request, &sha).is_ok());
        for field in ["force", "current", "id", "solution", "childhash", "case", "status"] {
            let mut changed = result.clone();
            match field {
                "force" => changed["pm_array_force_n"][0] = json!(4.),
                "case" => changed["qualified_case"]["case_id"] = json!("other-case"),
                "status" => changed["status"] = json!("passed-fresh-recorded-geometry-dc-request-only"),
                "current" => changed["eligibility"]["current_a"] = json!(0.5),
                "id" => changed["eligibility"]["request_id"] = json!("old-request"),
                "solution" => changed["fresh_solution"] = json!("../old-state.sol"),
                _ => changed["fresh_solve_summary_sha256"] = json!("changed"),
            }
            save(&changed);
            assert!(
                verify_result(job, &request, &sha).is_err(),
                "admitted {field}"
            );
        }
        save(&result);
        fs::write(job.join("request.json"), b"changed").unwrap();
        assert!(verify_result(job, &request, &sha)
            .unwrap_err()
            .contains("stale"));
        fs::write(job.join("request.json"), &bytes).unwrap();
        fs::write(
            job.join("result/fresh-magnetic-solve/state.sol"),
            b"changed",
        )
        .unwrap();
        assert!(verify_result(job, &request, &sha).is_err());
    }

    #[test]
    fn capability_lists_only_registered_cases_with_declared_placement() {
        let dir = tempfile::tempdir().unwrap();
        assert!(qualified_cases(dir.path()).unwrap().is_empty());
        fs::write(dir.path().join(REGISTRY), br#"{"schema":"other","cases":[]}"#).unwrap();
        assert!(qualified_cases(dir.path()).is_err());
        fs::write(dir.path().join(REGISTRY), serde_json::to_vec(&json!({"schema":"dc-qualified-linear-cases-v1","cases":[
            {"case_id":"a","label":"A","audit_sha256":"x","declaration":{"material_model":{},"return_geometry":{}},"live":{"nominal":{}}},
            {"case_id":"b","label":"undeclared"}]})).unwrap()).unwrap();
        let cases = qualified_cases(dir.path()).unwrap();
        assert_eq!(cases.len(), 1);
        assert_eq!(cases[0]["case_id"], "a");
        // Worker-side live inputs are never exposed through IPC.
        assert!(cases[0].get("live").is_none());
    }

    #[test]
    fn applicability_verifier_rejects_stale_or_force_bearing_reports() {
        let request = json!({"request_id":"inspect"});
        let valid = json!({"schema":"finite-dc-applicability-v1","request_id":"inspect","request_sha256":"sha",
            "state":"preparation-required","source_status":"unqualified","force_status":"unqualified",
            "reason":"Offline qualification required","qualified_case":null});
        assert!(verify_applicability(valid.clone(), &request, "sha").is_ok());
        for (key, value) in [("request_sha256", json!("old")), ("request_id", json!("other")),
            ("state", json!("qualified")), ("source_status", json!("qualified-exact-basis")), ("pm_array_force_n", json!([1.,2.,3.]))] {
            let mut changed = valid.clone(); changed[key] = value;
            assert!(verify_applicability(changed, &request, "sha").is_err());
        }
    }

    #[test]
    fn inspection_and_numerical_job_share_one_owned_worker_policy() {
        let jobs = DcJobs::default();
        let dir = tempfile::tempdir().unwrap();
        let permit = jobs.begin_inspection().unwrap();
        assert!(jobs.begin_inspection().is_err());
        assert!(jobs.launch(runtime(dir.path(), "pass"), json!({"request_id":"blocked"}), Duration::from_secs(3))
            .unwrap_err().contains("applicability check"));
        assert!(!dir.path().join("dc-desktop-jobs").exists());
        drop(permit);
        let running = jobs.launch(runtime(dir.path(), "import time;time.sleep(60)"), json!({"request_id":"active"}), Duration::from_secs(3)).unwrap();
        assert!(jobs.begin_inspection().is_err());
        jobs.cancel(&running.job_id).unwrap();
        wait(&jobs, &running.job_id);
        let permit = jobs.begin_inspection().unwrap();
        drop(permit);
        jobs.shutdown();
        assert!(jobs.begin_inspection().is_err());
    }

    #[test]
    fn shutdown_stops_owned_inspection_and_its_child() {
        let dir = tempfile::tempdir().unwrap();
        let rt = runtime(dir.path(), "pass");
        fs::write(dir.path().join("dc_applicability.py"), "import subprocess,sys,time\nfrom pathlib import Path\np=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\nPath(sys.argv[2]).with_name('nested.pid').write_text(str(p.pid))\ntime.sleep(60)\n").unwrap();
        let jobs = DcJobs::default(); jobs.inspecting.store(true, Ordering::SeqCst);
        let stopped = jobs.shutting_down.clone(); let flag = jobs.inspecting.clone();
        let thread = std::thread::spawn(move || {
            let _permit = InspectionPermit(flag);
            inspect_actual_request(rt, json!({"request_id":"inspect"}), stopped)
        });
        let start = Instant::now();
        let pid_path = loop {
            let path = fs::read_dir(dir.path().join("dc-desktop-inspections")).ok()
                .and_then(|mut paths| paths.next()).and_then(|path| path.ok()).map(|entry| entry.path().join("nested.pid"));
            if let Some(path) = path { if path.exists() { break path; } }
            assert!(start.elapsed() < Duration::from_secs(3));
            std::thread::sleep(Duration::from_millis(10));
        };
        jobs.shutdown(); assert!(thread.join().unwrap().unwrap_err().contains("shutdown"));
        let pid = fs::read_to_string(pid_path).unwrap();
        let output = Command::new("ps").args(["-o","stat=","-p",pid.trim()]).output().unwrap();
        let state = String::from_utf8_lossy(&output.stdout);
        assert!(state.trim().is_empty() || state.trim().starts_with('Z'));
        assert!(inspect_actual_request(runtime(dir.path(), "pass"), json!({"request_id":"late"}), jobs.shutting_down.clone()).unwrap_err().contains("shutting down"));
    }

    #[test]
    fn normal_shutdown_stops_active_job() {
        let dir = tempfile::tempdir().unwrap();
        let jobs = DcJobs::default();
        let initial = jobs
            .launch(
                runtime(dir.path(), "import time;time.sleep(60)"),
                json!({"request_id":"shutdown"}),
                TIMEOUT,
            )
            .unwrap();
        jobs.shutdown();
        assert_eq!(jobs.status(&initial.job_id).unwrap().state, "cancelled");
        assert!(jobs
            .launch(
                runtime(dir.path(), "pass"),
                json!({"request_id":"late-after-exit"}),
                TIMEOUT
            )
            .is_err());
    }

    #[test]
    #[ignore = "Explicit actual-project snapshot for independent geometry/source qualification"]
    fn export_saved_dc_geometry_for_independent_qualification() {
        let project_path = PathBuf::from(std::env::var_os("PCB_MOTOR_PROJECT_PATH").unwrap());
        let original = fs::read(&project_path).unwrap();
        let project: Value = serde_json::from_slice(&original).unwrap();
        let index: usize = std::env::var("PCB_MOTOR_VERSION_INDEX").unwrap().parse().unwrap();
        let saved = &project["versions"][index]["state"];
        let config: crate::ipc::ProjectConfigStateIpc = serde_json::from_value(saved["config"].clone()).unwrap();
        let cad: Option<pcbmotorgen_export::cad_dxf::CadGeometry> = serde_json::from_value(saved["cad_geometry"].clone()).unwrap();
        let qualification_only = std::env::var("PCB_MOTOR_DC_QUALIFY_CIRCULAR").as_deref() == Ok("1");
        let snapshot = if qualification_only {
            // This branch is available only in this explicitly run offline test,
            // never through the production IPC command's supported-case gate.
            let cad = cad.as_ref().expect("circular qualification expects an actual imported source");
            let core = config.to_linear_motor_ipc().to_core();
            let board = super::super::cad_source::CadBoard::new(cad,&core).unwrap();
            pcbmotorgen_simulation::dc_geometry::circular_qualification_snapshot(&board.simulation_input(cad,&core),
                &board.routing,&config.drive,&super::super::cad_source::CadBoard::drive_hints(cad)).unwrap()
        } else {
            tauri::async_runtime::block_on(super::super::physics::prepare_dc_winding_geometry(
                config.to_linear_motor_ipc(), config.drive, cad)).unwrap()
        };
        let output = PathBuf::from(std::env::var_os("PCB_MOTOR_DC_EXPORT_PATH").unwrap());
        let bytes = serde_json::to_vec_pretty(&snapshot).unwrap();
        File::options().create_new(true).write(true).open(&output).unwrap().write_all(&bytes).unwrap();
        assert_eq!(fs::read(&project_path).unwrap(), original);
        println!("{}",serde_json::to_string(&json!({"source_project":project_path,"source_sha256":hash(&original),
            "version_index":index,"imported":!saved["cad_geometry"].is_null(),"qualification_only":qualification_only,
            "snapshot":output,"snapshot_sha256":hash(&bytes)})).unwrap());
    }

    #[test]
    #[ignore = "Explicit actual saved-design applicability check; requires configured worker, project and declared study request"]
    fn real_saved_design_applicability_rebuilds_copper_without_a_force() {
        let runtime = Runtime::from_env().unwrap();
        let path = PathBuf::from(std::env::var_os("PCB_MOTOR_PROJECT_PATH").unwrap());
        let original = fs::read(&path).unwrap();
        let project: Value = serde_json::from_slice(&original).unwrap();
        let state = &project["versions"][1]["state"];
        let config: crate::ipc::ProjectConfigStateIpc = serde_json::from_value(state["config"].clone()).unwrap();
        let cad = serde_json::from_value(state["cad_geometry"].clone()).unwrap();
        let declared = read_json(&PathBuf::from(std::env::var_os("PCB_MOTOR_DC_STUDY_REQUEST_PATH").unwrap())).unwrap();
        let winding = tauri::async_runtime::block_on(super::super::physics::prepare_dc_winding_geometry(
            config.to_linear_motor_ipc(), config.drive, cad)).unwrap();
        assert_eq!(winding["routing"], declared["winding"]["routing"]);
        assert_eq!(winding["networks"], declared["winding"]["networks"]);
        let study = DcStudy { request_id:format!("inspect-real-{}",std::process::id()),
            material_model:declared["material_model"].clone(),return_geometry:declared["return_geometry"].clone(),
            current_a:0.1,pm_offset_x_m:0.,placement_acknowledged:true };
        study.validate().unwrap();
        let request = study.request(winding);
        let result = inspect_actual_request(runtime, request, Arc::new(AtomicBool::new(false))).unwrap();
        let expected = std::env::var("PCB_MOTOR_DC_EXPECT_APPLICABILITY_STATE").unwrap();
        assert_eq!(result["state"], expected);
        assert!(result.get("pm_array_force_n").is_none());
        assert_eq!(fs::read(path).unwrap(), original);
        println!("Actual saved-design applicability: {}", serde_json::to_string(&result).unwrap());
    }

    #[test]
    #[ignore = "Explicit bounded real FEM integration: requires configured pinned solver/evidence and PCB_MOTOR_PROJECT_PATH"]
    fn real_saved_geometry_desktop_job_recalculates_requested_force() {
        let runtime = Runtime::from_env().unwrap();
        let project: Value = serde_json::from_slice(
            &fs::read(std::env::var_os("PCB_MOTOR_PROJECT_PATH").unwrap()).unwrap(),
        )
        .unwrap();
        let state = &project["versions"][1]["state"];
        let config: crate::ipc::ProjectConfigStateIpc =
            serde_json::from_value(state["config"].clone()).unwrap();
        let cad = serde_json::from_value(state["cad_geometry"].clone()).unwrap();
        let original = read_json(
            &runtime
                .archive
                .join("dc-live-request-roundtrip-v1-20261021/request.json"),
        )
        .unwrap();
        // Only explicitly recorded material placement and return are taken from
        // this regression study. Copper is rebuilt from the original design.
        let winding =
            tauri::async_runtime::block_on(super::super::physics::prepare_dc_winding_geometry(
                config.to_linear_motor_ipc(),
                config.drive,
                cad,
            ))
            .unwrap();
        assert_eq!(winding["routing"], original["winding"]["routing"]);
        assert_eq!(winding["networks"], original["winding"]["networks"]);
        let study = DcStudy {
            request_id: format!("desktop-real-{}", std::process::id()),
            material_model: original["material_model"].clone(),
            return_geometry: original["return_geometry"].clone(),
            current_a: 0.1,
            pm_offset_x_m: 0.,
            placement_acknowledged: true,
        };
        study.validate().unwrap();
        let request = study.request(winding);
        let jobs = DcJobs::default();
        let initial = jobs
            .launch(runtime.clone(), request.clone(), TIMEOUT)
            .unwrap();
        println!("Real desktop job evidence: {}", initial.evidence_directory);
        let start = Instant::now();
        loop {
            let result = jobs.status(&initial.job_id).unwrap();
            if !result.active() {
                println!("{}", serde_json::to_string(&result).unwrap());
                assert_eq!(result.state, "completed", "{:?}", result.error);
                assert!(result.result.is_some());
                break;
            }
            assert!(start.elapsed() < Duration::from_secs(370));
            std::thread::sleep(Duration::from_millis(100));
        }
        let mut changed = request.clone();
        changed["request_id"] = json!(format!("desktop-unsupported-{}", std::process::id()));
        changed["winding"]["geometry_hints"]["layer_z_m"] = json!([0., -0.00081]);
        let unsupported = jobs.launch(runtime.clone(), changed, TIMEOUT).unwrap();
        let rejected = wait(&jobs, &unsupported.job_id);
        println!(
            "Unsupported desktop job evidence: {}",
            rejected.evidence_directory
        );
        assert_eq!(rejected.state, "failed");
        assert!(rejected.result.is_none());
        assert!(!Path::new(&rejected.evidence_directory)
            .join("result/fresh-magnetic-solve")
            .exists());
        assert!(jobs.status(&initial.job_id).is_err());

        let mut cancelled_request = request;
        cancelled_request["request_id"] = json!(format!("desktop-cancel-{}", std::process::id()));
        let cancelled = jobs.launch(runtime, cancelled_request, TIMEOUT).unwrap();
        let path = PathBuf::from(&cancelled.evidence_directory);
        let start = Instant::now();
        loop {
            let solving = path.join("result/fresh-magnetic-solve");
            let saved_state = fs::read_dir(&solving).ok().is_some_and(|files| {
                files
                    .flatten()
                    .any(|file| file.path().extension().is_some_and(|ext| ext == "sol"))
            });
            if saved_state {
                break;
            }
            assert!(
                jobs.status(&cancelled.job_id).unwrap().active(),
                "real solver exited before cancellation control"
            );
            assert!(start.elapsed() < Duration::from_secs(120));
            std::thread::sleep(Duration::from_millis(50));
        }
        jobs.cancel(&cancelled.job_id).unwrap();
        let stopped = wait(&jobs, &cancelled.job_id);
        println!(
            "Cancelled real desktop numerical job evidence: {}",
            stopped.evidence_directory
        );
        assert_eq!(stopped.state, "cancelled");
        assert!(stopped.result.is_none());
        for relative in [
            "desktop-worker.log.command.json",
            "result/fresh-magnetic-solve.log.command.json",
        ] {
            let receipt = read_json(&path.join(relative)).unwrap();
            let pid = receipt["pid"].as_u64().unwrap().to_string();
            let ps = Command::new("ps")
                .args(["-o", "stat=", "-p", &pid])
                .output()
                .unwrap();
            let state = String::from_utf8_lossy(&ps.stdout);
            assert!(
                state.trim().is_empty() || state.trim().starts_with('Z'),
                "real numerical child survived: {state}"
            );
        }
    }
}
