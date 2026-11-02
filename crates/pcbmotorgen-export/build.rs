//! Build script for the pcbmotorgen-export crate (KiCad 10 IPC protobuf codegen).
//!
//! Compiles the vendored KiCad IPC `.proto` files (under `proto/`) into Rust
//! modules. Parsing of the `.proto` sources is done with [`protox`], a pure-Rust
//! implementation of `protoc`, so no system `protoc` binary is required. The
//! resulting `FileDescriptorSet` is handed to [`prost_build`] which emits one
//! Rust source file per protobuf package into `OUT_DIR` (e.g. `kiapi.common.rs`,
//! `kiapi.board.types.rs`). This script then assembles a top-level umbrella
//! module (`kiapi.rs`) that wires those per-package files into a nested module
//! tree rooted at the shared `kiapi` package prefix; that umbrella is pulled
//! into the crate by `src/lib.rs`.
//!
//! Well-known types (`google/protobuf/any.proto`,
//! `google/protobuf/field_mask.proto`) are bundled by `protox`, and the
//! generated references resolve to the `prost-types` crate by default.

use std::collections::BTreeMap;
use std::fmt::Write as _;
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let manifest_dir = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR")?);
    let proto_root = manifest_dir.join("proto");

    let mut proto_files: Vec<PathBuf> = Vec::new();
    collect_protos(&proto_root, &mut proto_files)?;
    proto_files.sort();

    if proto_files.is_empty() {
        return Err("no .proto files found under proto/".into());
    }

    let proto_files_str: Vec<String> = proto_files
        .iter()
        .map(|p| p.to_string_lossy().into_owned())
        .collect();

    // Parse with protox (pure-Rust protoc). The include path is the proto root
    // so relative imports like `import "common/types/base_types.proto"` resolve.
    // protox bundles the well-known protos, so `google/protobuf/any.proto` and
    // `google/protobuf/field_mask.proto` resolve automatically.
    let file_descriptor_set = protox::compile(&proto_files_str, std::slice::from_ref(&proto_root))?;

    let mut config = prost_build::Config::new();
    config.compile_fds(file_descriptor_set)?;

    // prost-build writes one file per protobuf package but does not emit an
    // umbrella module. Build one ourselves from the package tree so the
    // generated cross-package references (e.g. `super::common::types::Distance`)
    // resolve with `common`/`board`/`schematic` as siblings at the top level.
    write_umbrella(&proto_files_str)?;

    println!("cargo:rerun-if-changed=build.rs");
    for p in &proto_files_str {
        println!("cargo:rerun-if-changed={}", p);
    }

    Ok(())
}

/// Collects all `.proto` files under `dir` recursively.
fn collect_protos(dir: &PathBuf, out: &mut Vec<PathBuf>) -> std::io::Result<()> {
    for entry in std::fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            collect_protos(&path, out)?;
        } else if path.extension().and_then(|e| e.to_str()) == Some("proto") {
            out.push(path);
        }
    }
    Ok(())
}

/// A node in the protobuf package tree.
struct PkgNode {
    children: BTreeMap<String, PkgNode>,
    /// The full dotted package name (e.g. `kiapi.common.types`) when this node
    /// corresponds exactly to a protobuf package; used to emit the matching
    /// `include!` of the per-package file prost-build wrote to `OUT_DIR`.
    full_package: Option<String>,
}

/// Writes `OUT_DIR/<prefix>.rs` (e.g. `kiapi.rs`): an umbrella module that
/// nests the per-package files prost-build generated, stripping the shared
/// leading package segment(s) so that the sub-modules (`common`, `board`,
/// `schematic`, ...) sit directly under the umbrella.
fn write_umbrella(proto_files_str: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    // Re-parse just to read the declared `package` of each file. protox already
    // validated these, so a cheap textual scan is sufficient here.
    let mut packages: Vec<Vec<String>> = Vec::new();
    for path in proto_files_str {
        let text = std::fs::read_to_string(path)?;
        if let Some(pkg) = text.lines().find_map(|l| {
            let l = l.trim();
            l.strip_prefix("package ").map(|r| r.trim_end_matches(';').trim())
        }) {
            let segs: Vec<String> = pkg.split('.').map(String::from).collect();
            if !segs.is_empty() {
                packages.push(segs);
            }
        }
    }
    packages.sort();
    packages.dedup();
    if packages.is_empty() {
        return Err("no package declarations found in .proto files".into());
    }

    // Compute the shared leading segments across all packages (e.g. ["kiapi"]).
    let prefix_len = packages
        .iter()
        .skip(1)
        .fold(packages[0].len(), |acc, p| {
            let mut i = 0;
            while i < acc && i < p.len() && packages[0][i] == p[i] {
                i += 1;
            }
            i
        });
    if prefix_len == 0 {
        return Err("proto packages do not share a common leading segment".into());
    }

    let umbrella_name = packages[0][..prefix_len].join(".");

    // Build the tree from the package segments with the shared prefix removed.
    let mut root = PkgNode {
        children: BTreeMap::new(),
        full_package: None,
    };
    for segs in &packages {
        let full = segs.join(".");
        let stripped = &segs[prefix_len..];
        let mut node = &mut root;
        for (i, seg) in stripped.iter().enumerate() {
            node = node
                .children
                .entry(seg.clone())
                .or_insert_with(|| PkgNode {
                    children: BTreeMap::new(),
                    full_package: None,
                });
            if i + 1 == stripped.len() {
                node.full_package = Some(full.clone());
            }
        }
    }

    let mut buf = String::new();
    writeln!(buf, "// This file is @generated by prost-build + build.rs.")?;
    write_node(&root, 0, &mut buf)?;

    let out_dir = std::env::var_os("OUT_DIR").ok_or("OUT_DIR environment variable is not set")?;
    let out_path = PathBuf::from(out_dir).join(format!("{}.rs", umbrella_name));
    if std::fs::read_to_string(&out_path).ok().as_deref() != Some(buf.as_str()) {
        std::fs::write(&out_path, buf)?;
    }
    Ok(())
}

fn write_node(node: &PkgNode, depth: usize, out: &mut String) -> std::fmt::Result {
    for (name, child) in &node.children {
        for _ in 0..depth {
            out.push_str("    ");
        }
        writeln!(out, "pub mod {} {{", name)?;
        if let Some(full) = &child.full_package {
            for _ in 0..(depth + 1) {
                out.push_str("    ");
            }
            writeln!(
                out,
                "include!(concat!(env!(\"OUT_DIR\"), \"/{}.rs\"));",
                full
            )?;
        }
        write_node(child, depth + 1, out)?;
        for _ in 0..depth {
            out.push_str("    ");
        }
        writeln!(out, "}}")?;
    }
    Ok(())
}
