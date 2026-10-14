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
    if path
        .extension()
        .and_then(|s| s.to_str())
        .map(str::to_ascii_lowercase)
        .as_deref()
        != Some("pmproj")
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
    let files: Vec<_> = workspace
        .files
        .iter()
        .map(|p| resolve(p))
        .collect::<Result<_, _>>()?;
    let active_file = workspace.active_file.as_deref().map(resolve).transpose()?;
    manifest(&path, files.clone(), active_file.clone())?;
    Ok(WorkspaceLoad {
        path: path.to_string_lossy().into_owned(),
        files,
        active_file,
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
        let data = manifest(&path, files, active_file)?;
        write_project_atomic(
            &path,
            &serde_json::to_string_pretty(&data).map_err(|e| e.to_string())?,
        )
    })
    .await
    .map_err(|e| e.to_string())?
}

fn collect_coil_files(dir: &Path, depth: usize, out: &mut Vec<String>) {
    if depth > 4 || out.len() >= 200 {
        return;
    }
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        if out.len() >= 200 {
            break;
        }
        let path = entry.path();
        let name = entry.file_name();
        let name_str = name.to_string_lossy();
        if name_str.starts_with('.')
            || matches!(name_str.as_ref(), "node_modules" | "target" | "dist")
        {
            continue;
        }
        if path.is_dir() {
            collect_coil_files(&path, depth + 1, out);
        } else if DocumentKind::from_path(&path).is_ok() {
            let resolved = std::fs::canonicalize(&path).unwrap_or(path);
            out.push(resolved.to_string_lossy().into_owned());
        }
    }
}

#[tauri::command]
pub async fn list_coil_files(directory: String) -> Result<Vec<String>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let dir = Path::new(&directory);
        if !dir.is_dir() {
            return Ok(Vec::new());
        }
        let mut files = Vec::new();
        collect_coil_files(dir, 0, &mut files);
        files.sort();
        files.dedup();
        Ok(files)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;

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
    fn lists_motor_and_sensor_files_in_folder_and_subfolders() {
        let dir = tempfile::tempdir().unwrap();
        let root_motor = dir.path().join("a.pmmotor");
        let sub = dir.path().join("sub");
        std::fs::create_dir(&sub).unwrap();
        let sub_sensor = sub.join("b.pmsensor");
        let ignored = dir.path().join("notes.txt");
        std::fs::write(&root_motor, "{}").unwrap();
        std::fs::write(&sub_sensor, "{}").unwrap();
        std::fs::write(&ignored, "ignore").unwrap();
        let mut found = Vec::new();
        collect_coil_files(dir.path(), 0, &mut found);
        found.sort();
        assert_eq!(found.len(), 2);
        assert!(found[0].ends_with("a.pmmotor"));
        assert!(found[1].ends_with("sub/b.pmsensor") || found[1].ends_with("sub\\b.pmsensor"));
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
