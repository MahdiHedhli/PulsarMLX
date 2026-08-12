//! Typed, content-addressed path resolution for M1-D packages.

use crate::json::sha256_bytes;
use crate::{FailureClass, RunnerError};
use serde::{Deserialize, Serialize};
use std::fs::{self, File};
use std::io::Read;
use std::path::{Component, Path, PathBuf};
use std::process::Command;

pub const PATH_RESOLUTION_CONTRACT_VERSION: &str = "f017-m1d-artifact-path-resolution-v1";

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PathKind {
    RepositoryRelative,
    PackageRelative,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ArtifactReference {
    pub path_kind: PathKind,
    pub symbolic_path: PathBuf,
    pub content_sha256: String,
    pub logical_role: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub package_artifact_id: Option<String>,
}

#[derive(Debug, Clone)]
pub struct ResolvedArtifact {
    pub bytes: Vec<u8>,
    pub canonical_path: PathBuf,
}

#[derive(Debug, Clone)]
pub struct TrustedRepositoryRoot {
    canonical: PathBuf,
    git_identity: String,
}

#[derive(Debug, Clone)]
pub struct PrivatePackageRoot {
    canonical: PathBuf,
}

impl TrustedRepositoryRoot {
    pub fn open(path: &Path) -> Result<Self, RunnerError> {
        reject_root_symlink(path, "m1d_repository_root_symlink")?;
        let canonical =
            fs::canonicalize(path).map_err(|error| path_error("m1d_repository_root", error))?;
        if !canonical.is_dir() {
            return Err(path_message(
                "m1d_repository_root",
                "repository root is not a directory",
            ));
        }
        let output = Command::new("git")
            .args(["-C"])
            .arg(&canonical)
            .args(["rev-parse", "HEAD"])
            .output()
            .map_err(|error| path_error("m1d_repository_identity", error))?;
        if !output.status.success() {
            return Err(path_message(
                "m1d_repository_identity",
                "trusted repository root has no readable Git identity",
            ));
        }
        let git_identity = String::from_utf8(output.stdout)
            .map_err(|error| path_error("m1d_repository_identity", error))?
            .trim()
            .to_owned();
        if git_identity != env!("PULSARMLX_SOURCE_SHA") {
            return Err(path_message(
                "m1d_repository_identity",
                format!(
                    "repository identity {git_identity} differs from compiled runtime {}",
                    env!("PULSARMLX_SOURCE_SHA")
                ),
            ));
        }
        Ok(Self {
            canonical,
            git_identity,
        })
    }

    pub fn identity(&self) -> &str {
        &self.git_identity
    }

    pub fn resolve(&self, reference: &ArtifactReference) -> Result<ResolvedArtifact, RunnerError> {
        if reference.path_kind != PathKind::RepositoryRelative
            || reference.package_artifact_id.is_some()
        {
            return Err(path_message(
                "m1d_path_namespace",
                "repository artifact has an ambiguous or incorrect path kind",
            ));
        }
        resolve_beneath(&self.canonical, reference)
    }
}

impl PrivatePackageRoot {
    pub fn from_package(path: &Path) -> Result<Self, RunnerError> {
        reject_root_symlink(path, "m1d_package_symlink")?;
        let canonical_package =
            fs::canonicalize(path).map_err(|error| path_error("m1d_package_path", error))?;
        let metadata = fs::metadata(&canonical_package)
            .map_err(|error| path_error("m1d_package_path", error))?;
        if !metadata.is_file() {
            return Err(path_message(
                "m1d_package_path",
                "projection package is not a regular file",
            ));
        }
        let canonical = canonical_package
            .parent()
            .ok_or_else(|| path_message("m1d_package_path", "package has no parent"))?
            .to_owned();
        Ok(Self { canonical })
    }

    pub fn resolve(&self, reference: &ArtifactReference) -> Result<ResolvedArtifact, RunnerError> {
        if reference.path_kind != PathKind::PackageRelative
            || reference
                .package_artifact_id
                .as_deref()
                .unwrap_or("")
                .is_empty()
        {
            return Err(path_message(
                "m1d_path_namespace",
                "private artifact has an ambiguous or incorrect path kind",
            ));
        }
        resolve_beneath(&self.canonical, reference)
    }
}

fn resolve_beneath(
    root: &Path,
    reference: &ArtifactReference,
) -> Result<ResolvedArtifact, RunnerError> {
    validate_symbolic_path(&reference.symbolic_path)?;
    let joined = root.join(&reference.symbolic_path);
    reject_relative_symlinks(root, &reference.symbolic_path)?;
    let canonical_path =
        fs::canonicalize(&joined).map_err(|error| path_error("m1d_artifact_missing", error))?;
    if !canonical_path.starts_with(root) {
        return Err(path_message(
            "m1d_path_escape",
            "artifact escapes its typed root",
        ));
    }
    let mut file =
        File::open(&canonical_path).map_err(|error| path_error("m1d_artifact_read", error))?;
    if !file
        .metadata()
        .map_err(|error| path_error("m1d_artifact_metadata", error))?
        .is_file()
    {
        return Err(path_message(
            "m1d_artifact_metadata",
            "artifact is not a regular file",
        ));
    }
    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes)
        .map_err(|error| path_error("m1d_artifact_read", error))?;
    if sha256_bytes(&bytes) != reference.content_sha256 {
        return Err(path_message(
            "m1d_artifact_hash",
            format!("{} content hash mismatch", reference.logical_role),
        ));
    }
    Ok(ResolvedArtifact {
        bytes,
        canonical_path,
    })
}

fn validate_symbolic_path(path: &Path) -> Result<(), RunnerError> {
    if path.as_os_str().is_empty() || path.is_absolute() {
        return Err(path_message(
            "m1d_symbolic_path",
            "symbolic artifact path must be a non-empty relative path",
        ));
    }
    if path
        .components()
        .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(path_message(
            "m1d_path_traversal",
            "symbolic artifact path contains a non-normal component",
        ));
    }
    Ok(())
}

fn reject_relative_symlinks(root: &Path, relative: &Path) -> Result<(), RunnerError> {
    let mut candidate = root.to_owned();
    for component in relative.components() {
        let Component::Normal(component) = component else {
            return Err(path_message(
                "m1d_path_traversal",
                "symbolic artifact path contains a non-normal component",
            ));
        };
        candidate.push(component);
        let metadata = fs::symlink_metadata(&candidate)
            .map_err(|error| path_error("m1d_artifact_missing", error))?;
        if metadata.file_type().is_symlink() {
            return Err(path_message(
                "m1d_artifact_symlink",
                "symlink components are forbidden in artifact paths",
            ));
        }
    }
    Ok(())
}

fn reject_root_symlink(path: &Path, code: &'static str) -> Result<(), RunnerError> {
    let metadata = fs::symlink_metadata(path).map_err(|error| path_error(code, error))?;
    if metadata.file_type().is_symlink() {
        return Err(path_message(code, "symlink roots are forbidden"));
    }
    Ok(())
}

fn path_error(code: &'static str, error: impl std::fmt::Display) -> RunnerError {
    path_message(code, error.to_string())
}

fn path_message(code: &'static str, message: impl Into<String>) -> RunnerError {
    RunnerError::new(FailureClass::InfrastructureEvidence, code, message)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT: AtomicU64 = AtomicU64::new(0);

    fn temp() -> PathBuf {
        let path = std::env::temp_dir().join(format!(
            "f017-artifact-paths-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&path).unwrap();
        path
    }

    fn package_reference(path: &str, bytes: &[u8]) -> ArtifactReference {
        ArtifactReference {
            path_kind: PathKind::PackageRelative,
            symbolic_path: path.into(),
            content_sha256: sha256_bytes(bytes),
            logical_role: "oracle".to_owned(),
            package_artifact_id: Some("f017-test-oracle".to_owned()),
        }
    }

    fn repository_root() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
    }

    #[test]
    fn repository_reference_requires_exact_git_root_and_content() {
        let root = TrustedRepositoryRoot::open(&repository_root()).unwrap();
        let bytes = fs::read(
            repository_root()
                .join("specs/017-rust-native-inference-runtime/contracts/m1d-q8-0-decoder-v1.json"),
        )
        .unwrap();
        let reference = ArtifactReference {
            path_kind: PathKind::RepositoryRelative,
            symbolic_path:
                "specs/017-rust-native-inference-runtime/contracts/m1d-q8-0-decoder-v1.json".into(),
            content_sha256: sha256_bytes(&bytes),
            logical_role: "decoder_contract".to_owned(),
            package_artifact_id: None,
        };
        assert_eq!(root.resolve(&reference).unwrap().bytes, bytes);

        let mut missing = reference.clone();
        missing.symbolic_path =
            "specs/017-rust-native-inference-runtime/contracts/missing.json".into();
        assert_eq!(
            root.resolve(&missing).unwrap_err().code,
            "m1d_artifact_missing"
        );
        let mut traversal = reference;
        traversal.symbolic_path = "../Cargo.toml".into();
        assert_eq!(
            root.resolve(&traversal).unwrap_err().code,
            "m1d_path_traversal"
        );
    }

    #[test]
    fn wrong_and_symlinked_repository_roots_fail_closed() {
        let wrong = temp();
        assert_eq!(
            TrustedRepositoryRoot::open(&wrong).unwrap_err().code,
            "m1d_repository_identity"
        );
        fs::remove_dir_all(wrong).unwrap();

        #[cfg(unix)]
        {
            use std::os::unix::fs::symlink;
            let parent = temp();
            let linked = parent.join("repository");
            symlink(repository_root(), &linked).unwrap();
            assert_eq!(
                TrustedRepositoryRoot::open(&linked).unwrap_err().code,
                "m1d_repository_root_symlink"
            );
            fs::remove_dir_all(parent).unwrap();
        }
    }

    #[test]
    fn package_relative_reference_is_content_addressed_and_relocatable() {
        for _ in 0..2 {
            let root = temp();
            fs::write(root.join("package.json"), b"{}").unwrap();
            fs::write(root.join("oracle.json"), b"oracle").unwrap();
            let package = PrivatePackageRoot::from_package(&root.join("package.json")).unwrap();
            assert_eq!(
                package
                    .resolve(&package_reference("oracle.json", b"oracle"))
                    .unwrap()
                    .bytes,
                b"oracle"
            );
            fs::remove_dir_all(root).unwrap();
        }
    }

    #[test]
    fn package_reference_rejects_traversal_hash_drift_and_ambiguity() {
        let root = temp();
        fs::write(root.join("package.json"), b"{}").unwrap();
        fs::write(root.join("oracle.json"), b"oracle").unwrap();
        let package = PrivatePackageRoot::from_package(&root.join("package.json")).unwrap();
        let mut traversal = package_reference("../oracle.json", b"oracle");
        assert_eq!(
            package.resolve(&traversal).unwrap_err().code,
            "m1d_path_traversal"
        );
        traversal.symbolic_path = "oracle.json".into();
        traversal.content_sha256 = "0".repeat(64);
        assert_eq!(
            package.resolve(&traversal).unwrap_err().code,
            "m1d_artifact_hash"
        );
        traversal.content_sha256 = sha256_bytes(b"oracle");
        traversal.package_artifact_id = None;
        assert_eq!(
            package.resolve(&traversal).unwrap_err().code,
            "m1d_path_namespace"
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn package_reference_rejects_symlink_escape() {
        use std::os::unix::fs::symlink;
        let root = temp();
        let outside = temp();
        fs::write(root.join("package.json"), b"{}").unwrap();
        fs::write(outside.join("oracle.json"), b"oracle").unwrap();
        symlink(outside.join("oracle.json"), root.join("oracle.json")).unwrap();
        let package = PrivatePackageRoot::from_package(&root.join("package.json")).unwrap();
        assert_eq!(
            package
                .resolve(&package_reference("oracle.json", b"oracle"))
                .unwrap_err()
                .code,
            "m1d_artifact_symlink"
        );
        fs::remove_dir_all(root).unwrap();
        fs::remove_dir_all(outside).unwrap();
    }
}
