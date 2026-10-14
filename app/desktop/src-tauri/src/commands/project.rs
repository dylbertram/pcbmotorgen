//! Coil document persistence. Motor and sensor files retain their own revisions.
//! Workspace manifests and legacy project conversion live in `workspace`.
//!
//! The frontend resolves the path with the native dialog plugin and hands
//! it over — the same convention as `register_routing_plugin` — while ALL
//! serialization, versioning, file I/O, and validation happen here / in
//! [`crate::ipc::project`]. Both handlers are thin wrappers over the pure
//! logic in [`crate::ipc::project`], executed on the blocking thread pool
//! so the main thread never waits on disk.

use std::time::{SystemTime, UNIX_EPOCH};

use tauri::{AppHandle, State};

use crate::ipc::*;
use crate::menu;
use std::path::Path;
use std::sync::Mutex;

pub(super) static PROJECT_FILES_LOCK: Mutex<()> = Mutex::new(());

fn now_ms() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

fn read_archive(path: &str) -> Result<(ProjectArchive, u32), String> {
    let json = std::fs::read_to_string(path).map_err(|e| match e.kind() {
        std::io::ErrorKind::NotFound => format!("could not open \"{path}\": file not found"),
        _ => format!("could not read \"{path}\": {e}"),
    })?;
    let kind = DocumentKind::from_path(Path::new(path))?;
    Ok((parse_document(&json, kind)?, 1))
}

fn write_archive(path: &str, archive: &ProjectArchive) -> Result<(), String> {
    let json = serialize_document(archive, DocumentKind::from_path(Path::new(path))?)?;
    write_project_atomic(Path::new(path), &json)
}

fn canonical_save_path(path: &str) -> Result<String, String> {
    let target = Path::new(path);
    let target = if target.exists() {
        std::fs::canonicalize(target).map_err(|e| e.to_string())?
    } else {
        let folder = target.parent().ok_or("Choose a folder for this file")?;
        std::fs::canonicalize(folder)
            .map_err(|e| format!("Could not open the file's folder: {e}"))?
            .join(target.file_name().ok_or("Choose a file name")?)
    };
    Ok(target.to_string_lossy().into_owned())
}

/// Publish a complete file without replacing an existing destination. The
/// temporary file lives in the destination folder, including cross-volume moves.
fn publish_project(path: &Path, bytes: &[u8], source: Option<&Path>) -> Result<(), String> {
    use std::io::Write;
    let parent = path.parent().ok_or("Choose a project folder")?;
    let mut temp = tempfile::NamedTempFile::new_in(parent)
        .map_err(|e| format!("Could not write to this folder: {e}"))?;
    temp.write_all(bytes)
        .map_err(|e| format!("Could not write project: {e}"))?;
    if let Some(source) = source {
        let permissions = std::fs::metadata(source)
            .map_err(|e| e.to_string())?
            .permissions();
        temp.as_file()
            .set_permissions(permissions)
            .map_err(|e| e.to_string())?;
    }
    temp.as_file().sync_all().map_err(|e| e.to_string())?;
    temp.persist_noclobber(path).map_err(|e| {
        if e.error.kind() == std::io::ErrorKind::AlreadyExists {
            "A file with this name already exists in that folder. Choose another name or folder."
                .into()
        } else {
            format!("Could not create project: {}", e.error)
        }
    })?;
    if let Some(source) = source {
        if let Err(e) = std::fs::remove_file(source) {
            let cleanup = std::fs::remove_file(path);
            return Err(format!(
                "Could not remove the original project: {e}. {}",
                if cleanup.is_ok() {
                    "The original file is unchanged."
                } else {
                    "A copy also remains in the chosen folder."
                }
            ));
        }
    }
    Ok(())
}

/// Move the saved artifact byte-for-byte, leaving the working draft untouched.
/// For an untitled project, create its first archive at the chosen location.
#[tauri::command]
pub async fn relocate_project(
    source_path: Option<String>,
    directory: String,
    name: String,
    project: ProjectStateIpc,
    active_version_id: Option<u32>,
) -> Result<SaveProjectResultIpc, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let _guard = PROJECT_FILES_LOCK
            .lock()
            .map_err(|_| "Project file lock failed")?;
        let name = name.trim();
        if name.is_empty()
            || name == "."
            || name == ".."
            || name
                .chars()
                .any(|c| c.is_control() || matches!(c, '/' | '\\' | ':'))
        {
            return Err("Enter a file name without slashes, colons, or control characters.".into());
        }
        let kind = match source_path.as_deref() {
            Some(path) => DocumentKind::from_path(Path::new(path))?,
            None => DocumentKind::from_path(Path::new(name))?,
        };
        let extension = format!(".{}", kind.extension());
        let named_extension = Path::new(name)
            .extension()
            .and_then(|s| s.to_str())
            .map(str::to_ascii_lowercase);
        if matches!(named_extension.as_deref(), Some("pmmotor" | "pmsensor" | "pmproj"))
            && !name.to_lowercase().ends_with(&extension)
        {
            return Err(format!(
                "Keep the .{} extension for this file type.",
                kind.extension()
            ));
        }
        let name = if name.to_lowercase().ends_with(&extension) {
            name.to_string()
        } else {
            format!("{name}{extension}")
        };
        if name.eq_ignore_ascii_case(&extension) {
            return Err("Enter a file name before the extension.".into());
        }
        let folder = std::fs::canonicalize(&directory)
            .map_err(|e| format!("Could not open project folder: {e}"))?;
        if !folder.is_dir() {
            return Err("Choose a folder for the project.".into());
        }
        let target = folder.join(name);
        let source = source_path
            .as_deref()
            .map(std::fs::canonicalize)
            .transpose()
            .map_err(|e| format!("Could not open original project: {e}"))?;
        let (archive, bytes) = if let Some(source) = &source {
            let bytes = std::fs::read(source).map_err(|e| e.to_string())?;
            let archive = parse_document(
                std::str::from_utf8(&bytes).map_err(|e| e.to_string())?,
                kind,
            )?;
            (archive, bytes)
        } else {
            let archive = ProjectArchive::new(project, now_ms());
            let bytes = serialize_document(&archive, kind)?.into_bytes();
            (archive, bytes)
        };
        let id = active_version_id.unwrap_or(archive.latest().info.id);
        archive.version(id)?;
        if source.as_deref() != Some(target.as_path()) {
            publish_project(&target, &bytes, source.as_deref())?;
        }
        Ok(SaveProjectResultIpc {
            path: target.to_string_lossy().into_owned(),
            format_version: 1,
            saved_at_unix_ms: archive.saved_at_unix_ms,
            active_version_id: id,
            versions: archive.summaries(),
        })
    })
    .await
    .map_err(|e| format!("relocate_project worker failed: {e}"))?
}

fn loaded_version(
    archive: &ProjectArchive,
    source: u32,
    id: Option<u32>,
) -> Result<LoadProjectResultIpc, String> {
    let version = match id {
        Some(id) => archive.version(id)?,
        None => archive.latest(),
    };
    Ok(LoadProjectResultIpc {
        project: version.project.clone(),
        source_format_version: source,
        format_version: 1,
        validation: design_validation(&version.project),
        active_version_id: version.info.id,
        versions: archive.summaries(),
    })
}

// ===========================================================================
// save_project — REAL (versioned envelope + atomic write)
// ===========================================================================

/// Internal revision writer for a typed coil document.
///
/// The artifact is written atomically (temp file + rename) so a failed or
/// interrupted save never truncates the previous file. Saving does NOT
/// require the design to pass validation — work-in-progress is saveable;
/// the load path reports validation findings instead of blocking.
#[tauri::command]
pub async fn save_project(
    path: String,
    project: ProjectStateIpc,
    source_path: Option<String>,
    active_version_id: Option<u32>,
    new_version: Option<bool>,
    description: Option<String>,
) -> Result<SaveProjectResultIpc, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let _guard = PROJECT_FILES_LOCK
            .lock()
            .map_err(|_| "Project file lock failed")?;
        let now = now_ms();
        let requested_kind = DocumentKind::from_path(Path::new(&path))?;
        let path = canonical_save_path(&path)?;
        let kind = DocumentKind::from_path(Path::new(&path))?;
        if kind != requested_kind {
            return Err("The destination points to a different document type.".into());
        }
        if let Some(source) = &source_path {
            if DocumentKind::from_path(Path::new(source))? != kind {
                return Err("Save As cannot change a motor document into a sensor document.".into());
            }
        }
        // An untitled design saved as a new version into an existing file must
        // append to that file, never replace its version history.
        let source_path = source_path.or_else(|| {
            (new_version.unwrap_or(false) && Path::new(&path).exists()).then(|| path.clone())
        });
        let (mut archive, active_version_id) = if let Some(source) = source_path {
            let mut archive = read_archive(&source)?.0;
            let id = archive.save(
                project,
                active_version_id,
                new_version.unwrap_or(false),
                description,
                now,
            )?;
            (archive, id)
        } else {
            let mut archive = ProjectArchive::new(project, now);
            if let Some(description) = description {
                archive.versions[0].info.description = description;
            }
            (archive, 1)
        };
        archive.format_version = PROJECT_FORMAT_VERSION;
        write_archive(&path, &archive)?;
        Ok(SaveProjectResultIpc {
            path,
            format_version: 1,
            saved_at_unix_ms: archive.saved_at_unix_ms,
            active_version_id,
            versions: archive.summaries(),
        })
    })
    .await
    .map_err(|e| format!("save_project worker failed: {e}"))?
}

/// Public save entry point always checks the editor's immutable document type.
#[tauri::command]
pub async fn save_document(
    path: String,
    document_type: DocumentKind,
    project: ProjectStateIpc,
    source_path: Option<String>,
    active_version_id: Option<u32>,
    new_version: Option<bool>,
    description: Option<String>,
) -> Result<SaveProjectResultIpc, String> {
    if DocumentKind::from_path(Path::new(&path))? != document_type {
        return Err(format!(
            "Save this file with a .{} extension.",
            document_type.extension()
        ));
    }
    save_project(
        path,
        project,
        source_path,
        active_version_id,
        new_version,
        description,
    )
    .await
}

#[tauri::command]
pub fn resolve_document_path(path: String) -> Result<String, String> {
    let canonical = std::fs::canonicalize(&path)
        .map_err(|e| format!("Could not open {path}: {e}"))?;
    DocumentKind::from_path(&canonical)?;
    Ok(canonical.to_string_lossy().into_owned())
}

// ===========================================================================
// load_project — REAL (parse + migrate + validate)
// ===========================================================================

/// Load a `.pmproj` artifact and return the state to restore plus the
/// load-time design validation findings.
///
/// Artifact-level failures (file missing, corrupt JSON, missing version,
/// newer format version, malformed state) are REJECTED with a specific
/// human-readable error and the frontend leaves the in-progress work
/// untouched. Design-level findings (an invalid but parseable design) are
/// returned in `validation` and do NOT block the restore.
#[tauri::command]
pub async fn load_project(
    path: String,
    version_id: Option<u32>,
) -> Result<LoadProjectResultIpc, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let _guard = PROJECT_FILES_LOCK
            .lock()
            .map_err(|_| "Project file lock failed")?;
        let (archive, source) = read_archive(&path)?;
        loaded_version(&archive, source, version_id)
    })
    .await
    .map_err(|e| format!("load_project worker failed: {e}"))?
}

/// Edit a description or delete one version without saving the working draft.
#[tauri::command]
pub async fn update_project_version(
    path: String,
    version_id: u32,
    active_version_id: Option<u32>,
    description: Option<String>,
    delete_version: Option<bool>,
) -> Result<LoadProjectResultIpc, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let _guard = PROJECT_FILES_LOCK
            .lock()
            .map_err(|_| "Project file lock failed")?;
        let (mut archive, _) = read_archive(&path)?;
        if delete_version.unwrap_or(false) {
            archive.delete(version_id, now_ms())?;
        } else {
            archive.describe(
                version_id,
                description.ok_or("A description is required")?,
                now_ms(),
            )?;
        }
        let active = active_version_id.filter(|id| archive.version(*id).is_ok());
        let result = loaded_version(&archive, PROJECT_FORMAT_VERSION, active)?;
        write_archive(&path, &archive)?;
        Ok(result)
    })
    .await
    .map_err(|e| format!("update_project_version worker failed: {e}"))?
}

// ===========================================================================
// set_recent_files — REAL (native menu mirror, kata eap8)
// ===========================================================================

/// Replace the contents of the native "Open Recent" File-menu submenu with
/// the webview-owned recents list (`paths`, most-recent-first, already
/// capped/pruned by the frontend recents store).
///
/// Sync command (deliberate deviation from the all-async inventory above):
/// muda/macOS requires menu mutations on the main thread, and the rebuild
/// is sub-millisecond, so the main thread is never meaningfully blocked.
/// The rebuild cannot fail for meaningful reasons; the string error keeps
/// the command signature trivial on the frontend side.
#[tauri::command]
pub fn set_recent_files(
    app: AppHandle,
    recent: State<'_, menu::RecentFiles>,
    paths: Vec<String>,
) -> Result<(), String> {
    menu::rebuild_recent_submenu(&app, &recent, &paths)
        .map_err(|e| format!("set_recent_files failed: {e}"))
}

// ===========================================================================
// file_exists — REAL (stat, kata eap8)
// ===========================================================================

/// Report whether `path` exists on disk. The frontend recents store uses
/// this to prune entries whose file no longer exists — at menu-build and
/// entry-open time (kata eap8), never as a background startup scan.
///
/// Sync command: a single stat is strictly cheaper than the async hop.
/// Deliberate deviation from the all-async inventory above.
#[tauri::command]
pub fn file_exists(path: String) -> bool {
    std::path::Path::new(&path).exists()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn public_save_rejects_a_different_document_type_without_writing() {
        tauri::async_runtime::block_on(async {
            let root = tempfile::tempdir().unwrap();
            let path = root.path().join("wrong.pmsensor");
            let result = save_document(
                path.to_string_lossy().into_owned(),
                DocumentKind::Motor,
                ProjectStateIpc::default(),
                None,
                None,
                None,
                None,
            ).await;
            assert!(result.unwrap_err().contains("pmmotor"));
            assert!(!path.exists());
        });
    }

    #[test]
    fn relocate_preserves_archive_bytes_and_never_overwrites() {
        tauri::async_runtime::block_on(async {
            let root = tempfile::tempdir().unwrap();
            let folder = root.path().to_string_lossy().into_owned();
            let created = relocate_project(
                None,
                folder.clone(),
                "Original.pmmotor".into(),
                ProjectStateIpc::default(),
                None,
            )
            .await
            .unwrap();
            assert_eq!(created.active_version_id, 1);
            let second = save_project(
                created.path.clone(),
                ProjectStateIpc::default(),
                Some(created.path.clone()),
                Some(1),
                Some(true),
                Some("Alternative".into()),
            )
            .await
            .unwrap();
            let before = std::fs::read(&second.path).unwrap();
            let dest_folder = root.path().join("Moved");
            std::fs::create_dir(&dest_folder).unwrap();
            let moved = relocate_project(
                Some(second.path.clone()),
                dest_folder.to_string_lossy().into_owned(),
                "Renamed.pmmotor".into(),
                ProjectStateIpc::default(),
                Some(1),
            )
            .await
            .unwrap();
            assert!(!Path::new(&second.path).exists());
            assert_eq!(std::fs::read(&moved.path).unwrap(), before);
            assert_eq!(moved.versions.len(), 2);
            assert_eq!(moved.active_version_id, 1);

            let collision = root.path().join("Existing.pmmotor");
            std::fs::write(&collision, b"Do not replace").unwrap();
            let failed = relocate_project(
                Some(moved.path.clone()),
                folder.clone(),
                "Existing".into(),
                ProjectStateIpc::default(),
                Some(1),
            )
            .await;
            assert!(failed.unwrap_err().contains("already exists"));
            assert_eq!(std::fs::read(&collision).unwrap(), b"Do not replace");
            assert_eq!(std::fs::read(&moved.path).unwrap(), before);
            assert!(relocate_project(
                None,
                folder.clone(),
                "Existing".into(),
                ProjectStateIpc::default(),
                None
            )
            .await
            .is_err());

            let noop = relocate_project(
                Some(moved.path.clone()),
                dest_folder.to_string_lossy().into_owned(),
                "Renamed".into(),
                ProjectStateIpc::default(),
                Some(1),
            )
            .await
            .unwrap();
            assert_eq!(noop.path, moved.path);
            assert_eq!(std::fs::read(&moved.path).unwrap(), before);
            for name in [
                "",
                ".",
                "..",
                "../escape",
                "nested/file",
                "bad\\name",
                "bad:name",
                ".pmmotor",
                "bad\nname",
            ] {
                assert!(
                    relocate_project(
                        Some(moved.path.clone()),
                        folder.clone(),
                        name.into(),
                        ProjectStateIpc::default(),
                        Some(1)
                    )
                    .await
                    .is_err(),
                    "Accepted invalid name {name:?}"
                );
            }
            assert_eq!(std::fs::read(&moved.path).unwrap(), before);
            assert!(relocate_project(
                Some(moved.path.clone()),
                root.path().join("missing").to_string_lossy().into_owned(),
                "Design".into(),
                ProjectStateIpc::default(),
                Some(1)
            )
            .await
            .is_err());
            assert_eq!(std::fs::read(&moved.path).unwrap(), before);
        });
    }

    #[test]
    fn file_round_trip_save_as_edit_and_delete_preserve_history() {
        tauri::async_runtime::block_on(async {
            let path = std::env::temp_dir()
                .join(format!(
                    "pcbmotorgen-versions-{}.pmmotor",
                    std::process::id()
                ))
                .to_string_lossy()
                .into_owned();
            let copy = format!("{path}.copy.pmmotor");
            let first = save_project(
                path.clone(),
                ProjectStateIpc::default(),
                None,
                None,
                Some(true),
                Some("Original".into()),
            )
            .await
            .unwrap();
            assert_eq!(first.active_version_id, 1);
            assert_eq!(first.versions.len(), 1);
            let mut second = ProjectStateIpc::default();
            second.config.desired_travel_mm = 40.0;
            let saved = save_project(
                path.clone(),
                second.clone(),
                Some(path.clone()),
                Some(1),
                Some(true),
                Some("Short track".into()),
            )
            .await
            .unwrap();
            assert_eq!(saved.versions.len(), 2);
            assert_eq!(
                load_project(path.clone(), None)
                    .await
                    .unwrap()
                    .active_version_id,
                2
            );
            let original = load_project(path.clone(), Some(1)).await.unwrap();
            assert_eq!(original.project.config.desired_travel_mm, 75.0);
            save_project(
                copy.clone(),
                original.project,
                Some(path.clone()),
                Some(1),
                Some(false),
                None,
            )
            .await
            .unwrap();
            assert_eq!(
                load_project(copy.clone(), None)
                    .await
                    .unwrap()
                    .active_version_id,
                1
            );
            assert_eq!(
                load_project(path.clone(), None)
                    .await
                    .unwrap()
                    .active_version_id,
                2
            );
            let updated = update_project_version(
                path.clone(),
                1,
                Some(2),
                Some("Updated original".into()),
                None,
            )
            .await
            .unwrap();
            assert_eq!(updated.active_version_id, 2);
            assert_eq!(
                load_project(path.clone(), None)
                    .await
                    .unwrap()
                    .active_version_id,
                1
            );
            let deleted = update_project_version(path.clone(), 2, Some(2), None, Some(true))
                .await
                .unwrap();
            assert_eq!(deleted.active_version_id, 1);
            assert_eq!(deleted.versions.len(), 1);
            let before = std::fs::read_to_string(&path).unwrap();
            assert!(
                update_project_version(path.clone(), 1, Some(1), None, Some(true))
                    .await
                    .is_err()
            );
            assert_eq!(std::fs::read_to_string(&path).unwrap(), before);
            let (_, source) = read_archive(&copy).unwrap();
            assert_eq!(source, 1);
            assert_eq!(
                load_project(copy.clone(), None)
                    .await
                    .unwrap()
                    .versions
                    .len(),
                2
            );
            std::fs::remove_file(path).unwrap();
            std::fs::remove_file(copy).unwrap();
        });
    }

    #[test]
    fn corrupt_source_is_not_overwritten_by_save() {
        tauri::async_runtime::block_on(async {
            let path = std::env::temp_dir()
                .join(format!(
                    "pcbmotorgen-corrupt-versions-{}.pmmotor",
                    std::process::id()
                ))
                .to_string_lossy()
                .into_owned();
            std::fs::write(&path, "corrupt original").unwrap();
            assert!(save_project(
                path.clone(),
                ProjectStateIpc::default(),
                Some(path.clone()),
                Some(1),
                Some(false),
                None
            )
            .await
            .is_err());
            assert_eq!(std::fs::read_to_string(&path).unwrap(), "corrupt original");
            std::fs::remove_file(path).unwrap();
        });
    }

    #[test]
    fn untitled_save_new_version_appends_to_an_existing_file() {
        tauri::async_runtime::block_on(async {
            let path = std::env::temp_dir()
                .join(format!(
                    "pcbmotorgen-append-version-{}.pmmotor",
                    std::process::id()
                ))
                .to_string_lossy()
                .into_owned();
            save_project(
                path.clone(),
                ProjectStateIpc::default(),
                None,
                None,
                None,
                Some("Existing".into()),
            )
            .await
            .unwrap();
            let appended = save_project(
                path.clone(),
                ProjectStateIpc::default(),
                None,
                None,
                Some(true),
                Some("New design".into()),
            )
            .await
            .unwrap();
            assert_eq!(appended.active_version_id, 2);
            assert_eq!(appended.versions.len(), 2);
            assert_eq!(
                load_project(path.clone(), Some(1))
                    .await
                    .unwrap()
                    .versions
                    .iter()
                    .find(|v| v.id == 1)
                    .unwrap()
                    .description,
                "Existing"
            );
            std::fs::remove_file(path).unwrap();
        });
    }
}
