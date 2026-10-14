//! Distinct coil documents. The legacy combined archive is only an internal
//! adapter for the existing revision operations, never the new disk format.
use super::project::{ProjectConfigStateIpc, ProjectStateIpc};
use super::project_versions::{parse_project_archive, ProjectArchive, ProjectVersionInfoIpc};
use pcbmotorgen_export::cad_dxf::CadGeometry;
use pcbmotorgen_routing::SensorConfig;
use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DocumentKind {
    Motor,
    Sensor,
}

impl DocumentKind {
    pub fn extension(self) -> &'static str {
        match self {
            Self::Motor => "pmmotor",
            Self::Sensor => "pmsensor",
        }
    }
    pub fn from_path(path: &Path) -> Result<Self, String> {
        match path
            .extension()
            .and_then(|s| s.to_str())
            .map(str::to_ascii_lowercase)
            .as_deref()
        {
            Some("pmmotor") => Ok(Self::Motor),
            Some("pmsensor") => Ok(Self::Sensor),
            _ => Err("Choose a .pmmotor or .pmsensor file.".into()),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "document_type", rename_all = "snake_case", deny_unknown_fields)]
enum CoilState {
    Motor {
        config: ProjectConfigStateIpc,
        mover_position_mm: f64,
        cad_geometry: Option<CadGeometry>,
    },
    Sensor {
        sensor_config: SensorConfig,
        sensor_cad_geometry: Option<CadGeometry>,
    },
}

impl CoilState {
    fn kind(&self) -> DocumentKind {
        match self {
            Self::Motor { .. } => DocumentKind::Motor,
            Self::Sensor { .. } => DocumentKind::Sensor,
        }
    }
    fn from_project(project: &ProjectStateIpc, kind: DocumentKind) -> Self {
        match kind {
            DocumentKind::Motor => Self::Motor {
                config: project.config.clone(),
                mover_position_mm: project.mover_position_mm,
                cad_geometry: project.cad_geometry.clone(),
            },
            DocumentKind::Sensor => Self::Sensor {
                sensor_config: project.sensor_config.clone(),
                sensor_cad_geometry: project.sensor_cad_geometry.clone(),
            },
        }
    }
    fn into_project(self) -> ProjectStateIpc {
        let mut project = ProjectStateIpc::default();
        match self {
            Self::Motor { config, mover_position_mm, cad_geometry } => {
                project.config = config;
                project.mover_position_mm = mover_position_mm;
                project.cad_geometry = cad_geometry;
            }
            Self::Sensor { sensor_config, sensor_cad_geometry } => {
                project.sensor_config = sensor_config;
                project.sensor_cad_geometry = sensor_cad_geometry;
            }
        }
        project
    }
}

#[derive(Serialize, Deserialize)]
struct CoilVersion {
    #[serde(flatten)]
    info: ProjectVersionInfoIpc,
    state: CoilState,
}

#[derive(Serialize, Deserialize)]
struct CoilFile {
    format: String,
    format_version: u32,
    document_type: DocumentKind,
    app_version: String,
    saved_at_unix_ms: i64,
    next_version_id: u32,
    versions: Vec<CoilVersion>,
}

pub fn serialize_document(archive: &ProjectArchive, kind: DocumentKind) -> Result<String, String> {
    serde_json::to_string_pretty(&CoilFile {
        format: "pcbmotorgen-coil".into(),
        format_version: 1,
        document_type: kind,
        app_version: archive.app_version.clone(),
        saved_at_unix_ms: archive.saved_at_unix_ms,
        next_version_id: archive.next_version_id,
        versions: archive.versions.iter().map(|v| CoilVersion {
            info: v.info.clone(),
            state: CoilState::from_project(&v.project, kind),
        }).collect(),
    })
    .map_err(|e| e.to_string())
}

pub fn parse_document(json: &str, expected: DocumentKind) -> Result<ProjectArchive, String> {
    let file: CoilFile = serde_json::from_str(json).map_err(|e| format!("Invalid coil document: {e}"))?;
    if file.format != "pcbmotorgen-coil" || file.format_version != 1 {
        return Err("Unsupported coil format. Update pcbmotorgen to open newer files.".into());
    }
    if file.document_type != expected || file.versions.iter().any(|v| v.state.kind() != expected) {
        return Err(format!("Document type does not match .{}; motor and sensor files are separate types.", expected.extension()));
    }
    let archive = ProjectArchive {
        format_version: super::project::PROJECT_FORMAT_VERSION,
        app_version: file.app_version,
        saved_at_unix_ms: file.saved_at_unix_ms,
        next_version_id: file.next_version_id,
        versions: file.versions.into_iter().map(|v| super::project_versions::ProjectVersionIpc {
            info: v.info,
            project: v.state.into_project(),
        }).collect(),
    };
    // Reuse the strict history validation, including unique IDs and timestamps.
    parse_project_archive(&serde_json::to_string(&archive).map_err(|e| e.to_string())?).map(|v| v.0)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn distinct_documents_preserve_history_without_other_design_state() {
        let mut archive = ProjectArchive::new(ProjectStateIpc::default(), 100);
        archive.save(ProjectStateIpc::default(), None, true, Some("second".into()), 200).unwrap();
        for kind in [DocumentKind::Motor, DocumentKind::Sensor] {
            let json = serialize_document(&archive, kind).unwrap();
            let restored = parse_document(&json, kind).unwrap();
            assert_eq!(restored.summaries(), archive.summaries());
            assert_eq!(restored.next_version_id, archive.next_version_id);
            let value: serde_json::Value = serde_json::from_str(&json).unwrap();
            let state = &value["versions"][0]["state"];
            assert_eq!(state.get("config").is_some(), kind == DocumentKind::Motor);
            assert_eq!(state.get("sensor_config").is_some(), kind == DocumentKind::Sensor);
            let other = if kind == DocumentKind::Motor { DocumentKind::Sensor } else { DocumentKind::Motor };
            assert!(parse_document(&json, other).is_err());
        }
    }

    #[test]
    fn rejects_foreign_newer_mixed_and_invalid_histories() {
        let archive = ProjectArchive::new(ProjectStateIpc::default(), 100);
        let json = serialize_document(&archive, DocumentKind::Motor).unwrap();
        let value: serde_json::Value = serde_json::from_str(&json).unwrap();
        for (field, replacement) in [("format", serde_json::json!("other")), ("format_version", serde_json::json!(2)), ("versions", serde_json::json!([]))] {
            let mut bad = value.clone();
            bad[field] = replacement;
            assert!(parse_document(&bad.to_string(), DocumentKind::Motor).is_err());
        }
        let mut mixed = value.clone();
        mixed["versions"][0]["state"]["document_type"] = serde_json::json!("sensor");
        assert!(parse_document(&mixed.to_string(), DocumentKind::Motor).is_err());
        let mut duplicate = value;
        let first = duplicate["versions"][0].clone();
        duplicate["versions"].as_array_mut().unwrap().push(first);
        assert!(parse_document(&duplicate.to_string(), DocumentKind::Motor).is_err());
    }

    #[test]
    fn sensor_configuration_is_not_replaced_with_defaults() {
        let mut state = ProjectStateIpc::default();
        state.sensor_config.lambda_mm = 240.0;
        let archive = ProjectArchive::new(state, 100);
        let restored = parse_document(&serialize_document(&archive, DocumentKind::Sensor).unwrap(), DocumentKind::Sensor).unwrap();
        assert_eq!(restored.latest().project.sensor_config.lambda_mm, 240.0);
    }
}
