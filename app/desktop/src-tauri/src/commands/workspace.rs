//! Workspace manifests reference coil documents; they never contain revisions.
use super::project::PROJECT_FILES_LOCK;
use crate::ipc::*;
use serde::{Deserialize, Serialize};
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};

#[derive(Default)]
pub struct ExitApproval(pub AtomicBool);

/// Called only after the frontend's save/discard/cancel flow approves exit.
#[tauri::command]
pub fn quit_app(app: tauri::AppHandle, approval: tauri::State<'_, ExitApproval>) {
    approval.inner().0.store(true, Ordering::SeqCst);
    app.exit(0);
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkspaceFile {
    pub format: String,
    pub format_version: u32,
    pub files: Vec<String>,
    pub active_file: Option<String>,
}

#[derive(Serialize)]
pub struct WorkspaceLoad {
    path: String,
    files: Vec<String>,
    active_file: Option<String>,
    legacy: bool,
}

fn absolute(path: &Path) -> Result<PathBuf, String> {
    let path = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|e| e.to_string())?
            .join(path)
    };
    let mut normalized = PathBuf::new();
    for part in path.components() {
        match part {
            Component::CurDir => {}
            Component::ParentDir => {
                normalized.pop();
            }
            _ => normalized.push(part),
        }
    }
    Ok(normalized)
}

fn relative(path: &Path, base: &Path) -> Result<String, String> {
    let target = absolute(path)?;
    let base = absolute(base)?;
    let a: Vec<_> = target.components().collect();
    let b: Vec<_> = base.components().collect();
    let common = a.iter().zip(&b).take_while(|(a, b)| a == b).count();
    if common == 0 {
        return Err("Keep the workspace and its coil files on the same drive.".into());
    }
    let mut result = PathBuf::new();
    for _ in common..b.len() {
        result.push("..");
    }
    for part in &a[common..] {
        result.push(part);
    }
    Ok(result.to_string_lossy().replace('\\', "/"))
}

fn manifest(
    path: &Path,
    files: Vec<String>,
    active: Option<String>,
) -> Result<WorkspaceFile, String> {
    if path.extension().and_then(|s| s.to_str())
        .map(str::to_ascii_lowercase).as_deref() != Some("pmproj")
    {
        return Err("Save the workspace with a .pmproj extension.".into());
    }
    let base = path.parent().ok_or("Choose a workspace folder")?;
    let mut paths = Vec::new();
    for file in files {
        DocumentKind::from_path(Path::new(&file))?;
        let reference = relative(Path::new(&file), base)?;
        if paths.contains(&reference) {
            return Err("The workspace contains a duplicate file.".into());
        }
        paths.push(reference);
    }
    let active = active.map(|p| relative(Path::new(&p), base)).transpose()?;
    if active.as_ref().is_some_and(|p| !paths.contains(p)) {
        return Err("The active file is not in the workspace.".into());
    }
    Ok(WorkspaceFile {
        format: "pcbmotorgen-workspace".into(),
        format_version: 1,
        files: paths,
        active_file: active,
    })
}

fn read_workspace(path: &str) -> Result<WorkspaceLoad, String> {
    let json = std::fs::read_to_string(path).map_err(|e| format!("Could not open workspace: {e}"))?;
    let value: serde_json::Value = serde_json::from_str(&json).map_err(|e| e.to_string())?;
    let path = absolute(Path::new(path))?;
    if value.get("format").is_none() {
        parse_project_archive(&json)?;
        return Ok(WorkspaceLoad {
            path: path.to_string_lossy().into_owned(),
            files: vec![],
            active_file: None,
            legacy: true,
        });
    }
    let workspace: WorkspaceFile = serde_json::from_value(value)
        .map_err(|e| format!("Invalid workspace: {e}"))?;
    if workspace.format != "pcbmotorgen-workspace" || workspace.format_version != 1 {
        return Err("Unsupported workspace format. Update pcbmotorgen to open newer files.".into());
    }
    let base = path.parent().ok_or("Workspace has no folder")?;
    let resolve = |p: &str| -> Result<String, String> {
        if Path::new(p).is_absolute() {
            return Err("Workspace references must be relative paths.".into());
        }
        let resolved = absolute(&base.join(p))?;
        let resolved = std::fs::canonicalize(&resolved).unwrap_or(resolved);
        DocumentKind::from_path(&resolved)?;
        Ok(resolved.to_string_lossy().into_owned())
    };
    let files: Vec<_> = workspace.files.iter()
        .map(|p| resolve(p)).collect::<Result<_, _>>()?;
    let active_file = workspace.active_file.as_deref().map(resolve).transpose()?;
    manifest(&path, files.clone(), active_file.clone())?;
    Ok(WorkspaceLoad {
        path: path.to_string_lossy().into_owned(),
        files,
        active_file,
        legacy: false,
    })
}

#[tauri::command]
pub async fn load_workspace(path: String) -> Result<WorkspaceLoad, String> {
    tauri::async_runtime::spawn_blocking(move || read_workspace(&path))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
pub async fn save_workspace(
    path: String,
    files: Vec<String>,
    active_file: Option<String>,
) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let _guard = PROJECT_FILES_LOCK.lock().map_err(|_| "File lock failed")?;
        let path = absolute(Path::new(&path))?;
        // Never silently replace a legacy combined design with a manifest.
        if path.exists() && read_workspace(&path.to_string_lossy())?.legacy {
            return Err("Choose a new workspace path. The legacy project must remain unchanged.".into());
        }
        let data = manifest(&path, files, active_file)?;
        write_project_atomic(
            &path,
            &serde_json::to_string_pretty(&data).map_err(|e| e.to_string())?,
        )
    })
    .await
    .map_err(|e| e.to_string())?
}

fn publish_new(path: &Path, json: &str) -> Result<(), String> {
    use std::io::Write;
    let mut temp = tempfile::NamedTempFile::new_in(path.parent().ok_or("Choose a folder")?)
        .map_err(|e| e.to_string())?;
    temp.write_all(json.as_bytes()).map_err(|e| e.to_string())?;
    temp.as_file().sync_all().map_err(|e| e.to_string())?;
    temp.persist_noclobber(path)
        .map_err(|e| format!("Could not create {}: {}", path.display(), e.error))?;
    Ok(())
}

fn migrate(source: &str, destination: &str) -> Result<WorkspaceLoad, String> {
    let destination = absolute(Path::new(destination))?;
    let source = absolute(Path::new(source))?;
    if source == destination {
        return Err("Choose a new workspace path; the original project is kept unchanged.".into());
    }
    let legacy = std::fs::read_to_string(source).map_err(|e| e.to_string())?;
    let archive = parse_project_archive(&legacy)?.0;
    let motor = destination.with_extension("pmmotor");
    let sensor = destination.with_extension("pmsensor");
    let files = vec![
        motor.to_string_lossy().into_owned(),
        sensor.to_string_lossy().into_owned(),
    ];
    let data = manifest(&destination, files.clone(), Some(files[0].clone()))?;
    for path in [&destination, &motor, &sensor] {
        if path.exists() {
            return Err(format!("{} already exists. Choose a different workspace name.", path.display()));
        }
    }
    // Publish the manifest last. On failure remove only files created here.
    publish_new(&motor, &serialize_document(&archive, DocumentKind::Motor)?)?;
    if let Err(e) = publish_new(&sensor, &serialize_document(&archive, DocumentKind::Sensor)?) {
        let _ = std::fs::remove_file(&motor);
        return Err(e);
    }
    if let Err(e) = publish_new(
        &destination,
        &serde_json::to_string_pretty(&data).map_err(|e| e.to_string())?,
    ) {
        let _ = std::fs::remove_file(&motor);
        let _ = std::fs::remove_file(&sensor);
        return Err(e);
    }
    read_workspace(&destination.to_string_lossy())
}

#[tauri::command]
pub async fn migrate_workspace(
    source: String,
    destination: String,
) -> Result<WorkspaceLoad, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let _guard = PROJECT_FILES_LOCK.lock().map_err(|_| "File lock failed")?;
        migrate(&source, &destination)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn migration_preserves_original_and_every_revision() {
        let dir = tempfile::tempdir().unwrap();
        let source = dir.path().join("old.pmproj");
        let destination = dir.path().join("new.pmproj");
        let mut state = ProjectStateIpc::default();
        state.sensor_config.lambda_mm = 240.0;
        state.cad_geometry = Some(pcbmotorgen_export::cad_dxf::CadGeometry {
            routing: pcbmotorgen_routing::RoutingResult {
                segments: vec![pcbmotorgen_routing::RouteSegment {
                    start: pcbmotorgen_routing::Point::new(1.0, 2.0),
                    end: pcbmotorgen_routing::Point::new(3.0, 2.0),
                    layer: 0,
                    net: "A".into(),
                    is_active: true,
                }],
                ..Default::default()
            },
            layer_z_mm: vec![-0.8, 0.8],
            trace_width_mm: 0.2,
            source_file_name: Some("motor.dxf".into()),
            source_layer_coils: Default::default(),
            coil_terminals: Default::default(),
        });
        state.sensor_cad_geometry = state.cad_geometry.clone();
        state.sensor_cad_geometry.as_mut().unwrap().routing.segments[0].net = "CL1".into();
        let mut archive = ProjectArchive::new(state.clone(), 100);
        archive.save(
            ProjectStateIpc::default(), None, true, Some("revision two".into()), 200,
        ).unwrap();
        let original = serde_json::to_string(&archive).unwrap();
        std::fs::write(&source, &original).unwrap();
        let loaded = migrate(source.to_str().unwrap(), destination.to_str().unwrap()).unwrap();
        assert!(!loaded.legacy);
        assert_eq!(std::fs::read_to_string(&source).unwrap(), original);
        for file in loaded.files {
            let kind = DocumentKind::from_path(Path::new(&file)).unwrap();
            let restored = parse_document(&std::fs::read_to_string(file).unwrap(), kind).unwrap();
            assert_eq!(restored.summaries(), archive.summaries());
            let restored = &restored.version(1).unwrap().project;
            if kind == DocumentKind::Motor {
                assert_eq!(
                    serde_json::to_value(&restored.cad_geometry).unwrap(),
                    serde_json::to_value(&state.cad_geometry).unwrap(),
                );
            } else {
                assert_eq!(restored.sensor_config.lambda_mm, 240.0);
                assert_eq!(
                    serde_json::to_value(&restored.sensor_cad_geometry).unwrap(),
                    serde_json::to_value(&state.sensor_cad_geometry).unwrap(),
                );
            }
        }
        assert!(migrate(source.to_str().unwrap(), destination.to_str().unwrap()).is_err());
        let json = std::fs::read_to_string(destination).unwrap();
        assert!(!json.contains(dir.path().to_str().unwrap()));
    }
    #[test]
    fn workspace_save_as_rebases_relative_paths_and_missing_files_still_resolve() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("nested/project.pmproj");
        std::fs::create_dir(path.parent().unwrap()).unwrap();
        let motor = dir.path().join("missing.pmmotor").to_string_lossy().into_owned();
        let data = manifest(&path, vec![motor.clone()], Some(motor.clone())).unwrap();
        assert_eq!(data.files, vec!["../missing.pmmotor"]);
        std::fs::write(&path, serde_json::to_string(&data).unwrap()).unwrap();
        assert_eq!(read_workspace(path.to_str().unwrap()).unwrap().files, vec![motor]);
    }

    #[test]
    fn migrates_v1_and_never_overwrites_colliding_coil_files() {
        let dir = tempfile::tempdir().unwrap();
        let source = dir.path().join("legacy.pmproj");
        let destination = dir.path().join("new.pmproj");
        let legacy = ProjectFileEnvelope {
            format_version: 1,
            app_version: "old".into(),
            saved_at_unix_ms: 1234,
            state: ProjectStateIpc::default(),
        };
        std::fs::write(&source, serde_json::to_string(&legacy).unwrap()).unwrap();
        std::fs::write(destination.with_extension("pmsensor"), "keep me").unwrap();
        assert!(migrate(source.to_str().unwrap(), destination.to_str().unwrap()).is_err());
        assert!(!destination.with_extension("pmmotor").exists());
        assert!(!destination.exists());
        assert_eq!(std::fs::read_to_string(destination.with_extension("pmsensor")).unwrap(), "keep me");
        let target = dir.path().join("converted.pmproj");
        let loaded = migrate(source.to_str().unwrap(), target.to_str().unwrap()).unwrap();
        for file in loaded.files {
            let kind = DocumentKind::from_path(Path::new(&file)).unwrap();
            let archive = parse_document(&std::fs::read_to_string(file).unwrap(), kind).unwrap();
            assert_eq!(archive.latest().info.created_at_unix_ms, 1234);
        }
    }

    #[test]
    fn rejects_foreign_future_duplicate_and_absolute_references() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("project.pmproj");
        let valid = serde_json::json!({"format": "pcbmotorgen-workspace", "format_version": 1, "files": ["motor.pmmotor"], "active_file": "motor.pmmotor"});
        for (key, value) in [
            ("format", serde_json::json!("foreign")),
            ("format_version", serde_json::json!(2)),
            ("files", serde_json::json!(["motor.pmmotor", "motor.pmmotor"])),
            ("files", serde_json::json!(["/absolute.pmmotor"])),
            ("active_file", serde_json::json!("other.pmsensor")),
        ] {
            let mut bad = valid.clone();
            bad[key] = value;
            std::fs::write(&path, bad.to_string()).unwrap();
            assert!(read_workspace(path.to_str().unwrap()).is_err());
        }
    }
}
