//! Editable project versions stored together in a single .pmproj file.
use super::project::{ProjectFileEnvelope, ProjectStateIpc, PROJECT_FORMAT_VERSION};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProjectVersionInfoIpc {
    pub id: u32,
    pub description: String,
    pub created_at_unix_ms: i64,
    pub last_edited_at_unix_ms: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectVersionIpc {
    #[serde(flatten)]
    pub info: ProjectVersionInfoIpc,
    pub project: ProjectStateIpc,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectArchive {
    pub format_version: u32,
    pub app_version: String,
    pub saved_at_unix_ms: i64,
    pub next_version_id: u32,
    pub versions: Vec<ProjectVersionIpc>,
}

impl ProjectArchive {
    pub fn new(project: ProjectStateIpc, now: i64) -> Self {
        Self {
            format_version: PROJECT_FORMAT_VERSION,
            app_version: env!("CARGO_PKG_VERSION").into(),
            saved_at_unix_ms: now,
            next_version_id: 2,
            versions: vec![ProjectVersionIpc {
                info: ProjectVersionInfoIpc {
                    id: 1,
                    description: String::new(),
                    created_at_unix_ms: now,
                    last_edited_at_unix_ms: now,
                },
                project,
            }],
        }
    }

    pub fn latest(&self) -> &ProjectVersionIpc {
        // Parsers and mutations guarantee that at least one version remains.
        self.versions
            .iter()
            .max_by_key(|v| (v.info.last_edited_at_unix_ms, v.info.id))
            .unwrap()
    }

    pub fn version(&self, id: u32) -> Result<&ProjectVersionIpc, String> {
        self.versions
            .iter()
            .find(|v| v.info.id == id)
            .ok_or_else(|| format!("Version {id} no longer exists in this file."))
    }

    pub fn summaries(&self) -> Vec<ProjectVersionInfoIpc> {
        let mut versions: Vec<_> = self.versions.iter().map(|v| v.info.clone()).collect();
        versions.sort_by_key(|v| std::cmp::Reverse((v.last_edited_at_unix_ms, v.id)));
        versions
    }

    fn edited_time(&self, now: i64) -> i64 {
        now.max(self.latest().info.last_edited_at_unix_ms.saturating_add(1))
    }

    pub fn save(
        &mut self,
        project: ProjectStateIpc,
        id: Option<u32>,
        new_version: bool,
        description: Option<String>,
        now: i64,
    ) -> Result<u32, String> {
        let edited = self.edited_time(now);
        let id = if new_version {
            let id = self.next_version_id;
            self.next_version_id = id.checked_add(1).ok_or("Version ID limit reached")?;
            self.versions.push(ProjectVersionIpc {
                info: ProjectVersionInfoIpc {
                    id,
                    description: description.unwrap_or_default(),
                    created_at_unix_ms: edited,
                    last_edited_at_unix_ms: edited,
                },
                project,
            });
            id
        } else {
            let id = id.unwrap_or(self.latest().info.id);
            let version = self
                .versions
                .iter_mut()
                .find(|v| v.info.id == id)
                .ok_or("The active version was deleted. Reopen the file before saving.")?;
            version.project = project;
            version.info.last_edited_at_unix_ms = edited;
            if let Some(description) = description {
                version.info.description = description;
            }
            id
        };
        self.saved_at_unix_ms = edited;
        self.app_version = env!("CARGO_PKG_VERSION").into();
        Ok(id)
    }

    pub fn describe(&mut self, id: u32, description: String, now: i64) -> Result<(), String> {
        let edited = self.edited_time(now);
        let version = self
            .versions
            .iter_mut()
            .find(|v| v.info.id == id)
            .ok_or("Version no longer exists")?;
        version.info.description = description;
        version.info.last_edited_at_unix_ms = edited;
        self.saved_at_unix_ms = edited;
        Ok(())
    }

    pub fn delete(&mut self, id: u32, now: i64) -> Result<(), String> {
        self.version(id)?;
        if self.versions.len() == 1 {
            return Err("Keep at least one version in the project file.".into());
        }
        self.versions.retain(|v| v.info.id != id);
        self.saved_at_unix_ms = now.max(self.saved_at_unix_ms.saturating_add(1));
        Ok(())
    }
}

pub fn parse_project_archive(json: &str) -> Result<(ProjectArchive, u32), String> {
    let value: serde_json::Value = serde_json::from_str(json)
        .map_err(|e| format!("corrupt project file (invalid JSON): {e}"))?;
    let obj = value
        .as_object()
        .ok_or("corrupt project file: expected a JSON object")?;
    let raw_version = obj
        .get("format_version")
        .ok_or("not a pcbmotorgen project file: missing format_version")?
        .as_u64()
        .ok_or("corrupt project file: format_version must be a non-negative integer")?;
    if raw_version > u64::from(PROJECT_FORMAT_VERSION) {
        return Err(format!("project file was saved by a newer version of pcbmotorgen (format v{raw_version}); this build supports up to v{PROJECT_FORMAT_VERSION}. Update the app to open this file."));
    }
    let source = raw_version as u32;
    if source == 1 {
        let legacy: ProjectFileEnvelope = serde_json::from_value(value)
            .map_err(|e| format!("malformed project file (format v1): {e}"))?;
        return Ok((
            ProjectArchive::new(legacy.state, legacy.saved_at_unix_ms.max(0)),
            source,
        ));
    }
    if source != PROJECT_FORMAT_VERSION {
        return Err(format!("no migration path from project format v{source}"));
    }
    let archive: ProjectArchive = serde_json::from_value(value)
        .map_err(|e| format!("malformed project file (format v{source}): {e}"))?;
    if archive.versions.is_empty() {
        return Err("malformed project file: no saved versions".into());
    }
    let mut ids = std::collections::HashSet::new();
    for v in &archive.versions {
        if v.info.id == 0 || !ids.insert(v.info.id) || v.info.id >= archive.next_version_id {
            return Err("malformed project file: invalid or duplicate version IDs".into());
        }
        if v.info.created_at_unix_ms < 0
            || v.info.last_edited_at_unix_ms < v.info.created_at_unix_ms
            || v.info.last_edited_at_unix_ms > 8_640_000_000_000_000
        {
            return Err("malformed project file: invalid version timestamps".into());
        }
    }
    Ok((archive, source))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn design(travel: f64) -> ProjectStateIpc {
        let mut state = ProjectStateIpc::default();
        state.config.desired_travel_mm = travel;
        state
    }

    #[test]
    fn legacy_migration_preserves_state_and_save_time() {
        let legacy = ProjectFileEnvelope::build(&design(55.0), 1234);
        let (archive, source) =
            parse_project_archive(&serde_json::to_string(&legacy).unwrap()).unwrap();
        assert_eq!(source, 1);
        assert_eq!(archive.format_version, 2);
        assert_eq!(archive.latest().project.config.desired_travel_mm, 55.0);
        assert_eq!(archive.latest().info.created_at_unix_ms, 1234);
        assert_eq!(archive.latest().info.last_edited_at_unix_ms, 1234);
        assert_eq!(archive.next_version_id, 2);
    }

    #[test]
    fn saves_update_one_version_and_latest_uses_edited_not_created() {
        let mut archive = ProjectArchive::new(design(50.0), 100);
        assert_eq!(
            archive
                .save(design(60.0), Some(1), true, Some("Experiment".into()), 200)
                .unwrap(),
            2
        );
        archive
            .save(
                design(70.0),
                Some(1),
                false,
                Some("Revised original".into()),
                300,
            )
            .unwrap();
        assert_eq!(archive.versions.len(), 2);
        assert_eq!(archive.version(1).unwrap().info.created_at_unix_ms, 100);
        assert_eq!(archive.version(1).unwrap().info.last_edited_at_unix_ms, 300);
        assert_eq!(
            archive.version(2).unwrap().project.config.desired_travel_mm,
            60.0
        );
        assert_eq!(archive.latest().info.id, 1);
        let json = serde_json::to_string(&archive).unwrap();
        let (restored, source) = parse_project_archive(&json).unwrap();
        assert_eq!(source, 2);
        assert_eq!(restored.summaries(), archive.summaries());
        assert_eq!(restored.latest().project.config.desired_travel_mm, 70.0);
    }

    #[test]
    fn descriptions_edit_metadata_without_changing_saved_design() {
        let mut archive = ProjectArchive::new(design(50.0), 100);
        archive.save(design(60.0), None, true, None, 200).unwrap();
        archive.describe(1, "First design".into(), 300).unwrap();
        assert_eq!(archive.latest().info.id, 1);
        assert_eq!(archive.latest().info.created_at_unix_ms, 100);
        assert_eq!(archive.latest().project.config.desired_travel_mm, 50.0);
        assert_eq!(archive.latest().info.description, "First design");
    }

    #[test]
    fn selective_delete_keeps_other_versions_and_never_reuses_ids() {
        let mut archive = ProjectArchive::new(design(50.0), 100);
        archive.save(design(60.0), None, true, None, 200).unwrap();
        archive.save(design(70.0), None, true, None, 300).unwrap();
        archive.delete(2, 400).unwrap();
        assert!(archive.version(2).is_err());
        assert_eq!(
            archive.version(1).unwrap().project.config.desired_travel_mm,
            50.0
        );
        archive.delete(3, 500).unwrap();
        assert!(archive.delete(1, 600).is_err());
        assert_eq!(
            archive.save(design(80.0), None, true, None, 700).unwrap(),
            4
        );
    }

    #[test]
    fn equal_or_reversed_clock_still_makes_saved_version_latest() {
        let mut archive = ProjectArchive::new(design(50.0), 100);
        archive.save(design(60.0), None, true, None, 100).unwrap();
        archive
            .save(design(70.0), Some(1), false, None, 10)
            .unwrap();
        assert_eq!(archive.latest().info.id, 1);
        assert_eq!(archive.latest().info.last_edited_at_unix_ms, 102);
    }

    #[test]
    fn missing_version_does_not_mutate_archive() {
        let mut archive = ProjectArchive::new(design(50.0), 100);
        let before = serde_json::to_string(&archive).unwrap();
        assert!(archive
            .save(design(60.0), Some(99), false, None, 200)
            .is_err());
        assert!(archive.describe(99, "Missing".into(), 200).is_err());
        assert!(archive.delete(99, 200).is_err());
        assert_eq!(serde_json::to_string(&archive).unwrap(), before);
    }

    #[test]
    fn rejects_empty_duplicate_and_invalid_metadata() {
        let mut archive = ProjectArchive::new(design(50.0), 100);
        archive.versions.push(archive.versions[0].clone());
        assert!(parse_project_archive(&serde_json::to_string(&archive).unwrap()).is_err());
        archive.versions.pop();
        archive.versions[0].info.last_edited_at_unix_ms = 99;
        assert!(parse_project_archive(&serde_json::to_string(&archive).unwrap()).is_err());
        archive.versions.clear();
        assert!(parse_project_archive(&serde_json::to_string(&archive).unwrap()).is_err());
    }
}
