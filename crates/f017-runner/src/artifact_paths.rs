//! Typed, content-addressed path resolution for M1-D packages.

use crate::json::sha256_bytes;
use crate::{FailureClass, RunnerError};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs::{self, File};
use std::io::Read;
use std::path::{Component, Path, PathBuf};
use std::process::Command;

pub const PATH_RESOLUTION_CONTRACT_VERSION: &str = "f017-m1d-artifact-path-resolution-v1";
pub const TRUSTED_REPOSITORY_IDENTITY_VERSION: &str = "f017-trusted-repository-identity-v2";

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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct TrustedRepositoryIdentity {
    pub contract_version: String,
    pub contract_sha256: String,
    pub compiled_runtime_sha: String,
    pub tooling_sha: String,
    pub authorization_head_sha: String,
    pub runtime_drift_classification_sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RuntimeDriftEntry {
    pub status: String,
    pub category: String,
    pub path: String,
    pub permitted: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RuntimeDriftClassification {
    pub contract_version: String,
    pub compiled_runtime_sha: String,
    pub authorization_head_sha: String,
    pub entries: Vec<RuntimeDriftEntry>,
    pub category_counts: BTreeMap<String, u64>,
    pub runtime_semantics_unchanged: bool,
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

    /// Opens a repository under the staged-gate identity model. The binary's
    /// embedded source SHA proves the compiled runtime separately; this method
    /// proves the exact authorization checkout, ancestry, a clean worktree,
    /// and a deterministic no-runtime-drift classification.
    pub fn open_v2(
        path: &Path,
        identity: &TrustedRepositoryIdentity,
    ) -> Result<(Self, RuntimeDriftClassification), RunnerError> {
        reject_root_symlink(path, "m1e_repository_root_symlink")?;
        let canonical =
            fs::canonicalize(path).map_err(|error| path_error("m1e_repository_root", error))?;
        if !canonical.is_dir() {
            return Err(path_message(
                "m1e_repository_root",
                "repository root is not a directory",
            ));
        }
        if identity.contract_version != TRUSTED_REPOSITORY_IDENTITY_VERSION
            || !is_sha256(&identity.contract_sha256)
            || !is_git_sha(&identity.compiled_runtime_sha)
            || !is_git_sha(&identity.tooling_sha)
            || !is_git_sha(&identity.authorization_head_sha)
            || !is_sha256(&identity.runtime_drift_classification_sha256)
        {
            return Err(path_message(
                "m1e_repository_identity_contract",
                "trusted repository identity v2 binding is malformed",
            ));
        }
        let head = git_stdout(&canonical, &["rev-parse", "HEAD"])?;
        if head != identity.authorization_head_sha {
            return Err(path_message(
                "m1e_authorization_head",
                format!(
                    "repository HEAD {head} differs from authorized head {}",
                    identity.authorization_head_sha
                ),
            ));
        }
        let runtime_to_tooling = git_is_ancestor(
            &canonical,
            &identity.compiled_runtime_sha,
            &identity.tooling_sha,
        )?;
        let tooling_to_authorization = git_is_ancestor(
            &canonical,
            &identity.tooling_sha,
            &identity.authorization_head_sha,
        )?;
        if !runtime_to_tooling || !tooling_to_authorization {
            return Err(path_message(
                "m1e_repository_ancestry",
                "compiled runtime -> tooling -> authorization ancestry is invalid",
            ));
        }
        let dirty = git_stdout(
            &canonical,
            &["status", "--porcelain=v1", "--untracked-files=all"],
        )?;
        if !dirty.is_empty() {
            return Err(path_message(
                "m1e_repository_dirty",
                "trusted repository worktree is not clean",
            ));
        }
        let classification = classify_runtime_drift(
            &canonical,
            &identity.compiled_runtime_sha,
            &identity.authorization_head_sha,
        )?;
        let classification_bytes = serde_json::to_vec(&classification)
            .map_err(|error| path_error("m1e_runtime_drift_json", error))?;
        if sha256_bytes(&classification_bytes) != identity.runtime_drift_classification_sha256 {
            return Err(path_message(
                "m1e_runtime_drift_hash",
                "runtime-drift classification hash mismatch",
            ));
        }
        if !classification.runtime_semantics_unchanged {
            return Err(path_message(
                "m1e_runtime_drift",
                "authorization descendant contains execution-relevant drift",
            ));
        }
        Ok((
            Self {
                canonical,
                git_identity: head,
            },
            classification,
        ))
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

pub fn classify_runtime_drift(
    repository: &Path,
    compiled_runtime_sha: &str,
    authorization_head_sha: &str,
) -> Result<RuntimeDriftClassification, RunnerError> {
    let range = format!("{compiled_runtime_sha}..{authorization_head_sha}");
    let output = git_stdout(
        repository,
        &["diff", "--name-status", "--no-renames", &range],
    )?;
    let mut entries = Vec::new();
    let mut category_counts = BTreeMap::new();
    for line in output.lines().filter(|line| !line.trim().is_empty()) {
        let mut fields = line.splitn(2, '\t');
        let status = fields.next().unwrap_or("").to_owned();
        let path = fields.next().unwrap_or("").to_owned();
        if status.is_empty() || path.is_empty() {
            return Err(path_message(
                "m1e_runtime_drift_parse",
                "malformed Git name-status output",
            ));
        }
        let (category, permitted) = classify_path(&path);
        *category_counts.entry(category.to_owned()).or_insert(0) += 1;
        entries.push(RuntimeDriftEntry {
            status,
            category: category.to_owned(),
            path,
            permitted,
        });
    }
    let runtime_semantics_unchanged = entries.iter().all(|entry| entry.permitted);
    Ok(RuntimeDriftClassification {
        contract_version: TRUSTED_REPOSITORY_IDENTITY_VERSION.to_owned(),
        compiled_runtime_sha: compiled_runtime_sha.to_owned(),
        authorization_head_sha: authorization_head_sha.to_owned(),
        entries,
        category_counts,
        runtime_semantics_unchanged,
    })
}

fn classify_path(path: &str) -> (&'static str, bool) {
    if path.starts_with("docs/architecture/reviews/evidence/") {
        ("evidence", true)
    } else if path.starts_with("docs/architecture/reviews/") {
        ("docs_reviews", true)
    } else if path.starts_with("docs/") {
        ("docs", true)
    } else if path.starts_with("crates/quant/") {
        ("decoder", false)
    } else if path.starts_with("crates/stream/") || path.ends_with(".mm") {
        ("mlx_bridge", false)
    } else if path.starts_with("crates/f017-runner/src/artifact_paths.rs") {
        ("path_resolver", false)
    } else if path.starts_with("crates/f017-runner/src/") {
        ("execution_runner", false)
    } else if path.starts_with("crates/") {
        ("runtime_compute", false)
    } else if path.starts_with("scripts/research/tests/") || path.contains("/tests/") {
        ("tests", false)
    } else if path.starts_with("scripts/research/validate_") {
        ("evidence_validator", false)
    } else if path.starts_with("scripts/") {
        ("execution_tooling", false)
    } else if path.starts_with("specs/") {
        ("schema_contracts", false)
    } else if path.starts_with(".github/") {
        ("ci", false)
    } else {
        ("unclassified", false)
    }
}

fn git_stdout(repository: &Path, arguments: &[&str]) -> Result<String, RunnerError> {
    let output = Command::new("git")
        .args(["-C"])
        .arg(repository)
        .args(arguments)
        .output()
        .map_err(|error| path_error("m1e_repository_git", error))?;
    if !output.status.success() {
        return Err(path_message(
            "m1e_repository_git",
            String::from_utf8_lossy(&output.stderr).trim().to_owned(),
        ));
    }
    String::from_utf8(output.stdout)
        .map(|value| value.trim().to_owned())
        .map_err(|error| path_error("m1e_repository_git", error))
}

fn git_is_ancestor(
    repository: &Path,
    ancestor: &str,
    descendant: &str,
) -> Result<bool, RunnerError> {
    let status = Command::new("git")
        .args(["-C"])
        .arg(repository)
        .args(["merge-base", "--is-ancestor", ancestor, descendant])
        .status()
        .map_err(|error| path_error("m1e_repository_ancestry", error))?;
    Ok(status.success())
}

fn is_git_sha(value: &str) -> bool {
    value.len() == 40 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
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

    fn git(path: &Path, arguments: &[&str]) -> String {
        let output = Command::new("git")
            .args(["-C"])
            .arg(path)
            .args(arguments)
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "git failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        String::from_utf8(output.stdout).unwrap().trim().to_owned()
    }

    fn synthetic_repository() -> (PathBuf, String) {
        let root = temp();
        git(&root, &["init", "-q"]);
        git(&root, &["config", "user.email", "f017@example.invalid"]);
        git(&root, &["config", "user.name", "F017 test"]);
        fs::create_dir_all(root.join("crates/f017-runner/src")).unwrap();
        fs::create_dir_all(root.join("docs/architecture/reviews")).unwrap();
        fs::write(root.join("crates/f017-runner/src/lib.rs"), b"runtime-v1\n").unwrap();
        git(&root, &["add", "."]);
        git(&root, &["commit", "-q", "-m", "runtime"]);
        let runtime = git(&root, &["rev-parse", "HEAD"]);
        (root, runtime)
    }

    fn identity(root: &Path, runtime: &str, authorization: &str) -> TrustedRepositoryIdentity {
        let classification = classify_runtime_drift(root, runtime, authorization).unwrap();
        TrustedRepositoryIdentity {
            contract_version: TRUSTED_REPOSITORY_IDENTITY_VERSION.to_owned(),
            contract_sha256: "1".repeat(64),
            compiled_runtime_sha: runtime.to_owned(),
            tooling_sha: runtime.to_owned(),
            authorization_head_sha: authorization.to_owned(),
            runtime_drift_classification_sha256: sha256_bytes(
                &serde_json::to_vec(&classification).unwrap(),
            ),
        }
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
    fn identity_v2_accepts_exact_runtime_and_review_only_descendants() {
        let (root, runtime) = synthetic_repository();
        let exact = identity(&root, &runtime, &runtime);
        let (_, report) = TrustedRepositoryRoot::open_v2(&root, &exact).unwrap();
        assert!(report.entries.is_empty());

        fs::write(
            root.join("docs/architecture/reviews/authorization.md"),
            b"review only\n",
        )
        .unwrap();
        git(&root, &["add", "."]);
        git(&root, &["commit", "-q", "-m", "authorize"]);
        let authorization = git(&root, &["rev-parse", "HEAD"]);
        let descendant = identity(&root, &runtime, &authorization);
        let (_, report) = TrustedRepositoryRoot::open_v2(&root, &descendant).unwrap();
        assert!(report.runtime_semantics_unchanged);
        assert_eq!(report.category_counts.get("docs_reviews"), Some(&1));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn identity_v2_rejects_runtime_drift_wrong_head_non_ancestry_and_dirty_tree() {
        let (root, runtime) = synthetic_repository();
        fs::write(root.join("crates/f017-runner/src/lib.rs"), b"runtime-v2\n").unwrap();
        git(&root, &["add", "."]);
        git(&root, &["commit", "-q", "-m", "drift"]);
        let authorization = git(&root, &["rev-parse", "HEAD"]);
        let drift = identity(&root, &runtime, &authorization);
        assert_eq!(
            TrustedRepositoryRoot::open_v2(&root, &drift)
                .unwrap_err()
                .code,
            "m1e_runtime_drift"
        );

        let mut wrong_head = drift.clone();
        wrong_head.authorization_head_sha = runtime.clone();
        wrong_head.runtime_drift_classification_sha256 = sha256_bytes(
            &serde_json::to_vec(&classify_runtime_drift(&root, &runtime, &runtime).unwrap())
                .unwrap(),
        );
        assert_eq!(
            TrustedRepositoryRoot::open_v2(&root, &wrong_head)
                .unwrap_err()
                .code,
            "m1e_authorization_head"
        );

        fs::write(root.join("docs/dirty.md"), b"dirty\n").unwrap();
        let clean_identity = identity(&root, &runtime, &authorization);
        assert_eq!(
            TrustedRepositoryRoot::open_v2(&root, &clean_identity)
                .unwrap_err()
                .code,
            "m1e_repository_dirty"
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn identity_v2_rejects_stale_binary_attestation_and_unrelated_history() {
        let (root, runtime) = synthetic_repository();
        let authorization = git(&root, &["rev-parse", "HEAD"]);
        let mut stale = identity(&root, &runtime, &authorization);
        stale.runtime_drift_classification_sha256 = "0".repeat(64);
        assert_eq!(
            TrustedRepositoryRoot::open_v2(&root, &stale)
                .unwrap_err()
                .code,
            "m1e_runtime_drift_hash"
        );

        git(&root, &["checkout", "-q", "--orphan", "unrelated"]);
        for entry in fs::read_dir(&root).unwrap().flatten() {
            if entry.file_name() != ".git" {
                let path = entry.path();
                if path.is_dir() {
                    fs::remove_dir_all(path).unwrap();
                } else {
                    fs::remove_file(path).unwrap();
                }
            }
        }
        fs::write(root.join("unrelated.txt"), b"unrelated\n").unwrap();
        git(&root, &["add", "."]);
        git(&root, &["commit", "-q", "-m", "unrelated"]);
        let unrelated = git(&root, &["rev-parse", "HEAD"]);
        let fake = TrustedRepositoryIdentity {
            contract_version: TRUSTED_REPOSITORY_IDENTITY_VERSION.to_owned(),
            contract_sha256: "1".repeat(64),
            compiled_runtime_sha: runtime,
            tooling_sha: authorization,
            authorization_head_sha: unrelated,
            runtime_drift_classification_sha256: "1".repeat(64),
        };
        assert_eq!(
            TrustedRepositoryRoot::open_v2(&root, &fake)
                .unwrap_err()
                .code,
            "m1e_repository_ancestry"
        );
        fs::remove_dir_all(root).unwrap();
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
