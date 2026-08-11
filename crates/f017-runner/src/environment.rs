use crate::json::{parse_json_no_duplicates, sha256_file};
use crate::{FailureClass, RunnerError};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::ffi::CStr;
use std::fs;
use std::path::{Path, PathBuf};

pub const ENVIRONMENT_SCHEMA: &str = "pulsarmlx.f017.p1.admission-ready-environment";
pub const ENVIRONMENT_SCHEMA_VERSION: u32 = 1;
pub const REQUIRED_MLX_VERSION: &str = "0.31.2";
pub const REQUIRED_MLX_SOURCE_SHA: &str = "68cf2fddd8de5edd8ab3d926391772b2e2cedad8";
pub const REQUIRED_MLXC_VERSION: &str = "0.6.0";
pub const REQUIRED_MLXC_SOURCE_SHA: &str = "0726ca922fc902c4c61ef9c27d94132be418e945";

#[derive(Debug, Clone, Deserialize)]
pub struct EnvironmentManifest {
    pub schema: String,
    pub schema_version: u32,
    pub classification: String,
    pub build_environment: BuildEnvironment,
    pub pinned_installation: PinnedInstallation,
}

#[derive(Debug, Clone, Deserialize)]
pub struct BuildEnvironment {
    pub architecture: String,
    pub macos_version: String,
    pub macos_build: String,
    pub xcode_version: String,
    pub sdk_version: String,
    pub metal_compiler: String,
    pub compiler: String,
    pub rustc: String,
    pub cargo: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct PinnedInstallation {
    pub prefix: PathBuf,
    pub mlx: InstalledArtifact,
    pub mlx_c: InstalledMlxC,
    pub linkage: LinkageEvidence,
}

#[derive(Debug, Clone, Deserialize)]
pub struct InstalledArtifact {
    pub version: String,
    pub source_sha: String,
    pub library_sha256: String,
    pub architecture: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct InstalledMlxC {
    pub version: String,
    pub source_sha: String,
    pub library_sha256: String,
    pub header_sha256: String,
    pub architecture: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct LinkageEvidence {
    pub adapter_binary_links_mlxc: String,
    pub adapter_binary_links_mlx: String,
    pub mlxc_links_mlx: String,
    pub isolated_prefix_selected: bool,
    pub alternate_mlx_selected: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct LoadedLibraryEvidence {
    pub artifact: String,
    pub resolved_basename: String,
    pub actual_sha256: String,
    pub expected_sha256: String,
    pub architecture: String,
}

#[derive(Debug, Clone)]
pub struct ValidatedEnvironment {
    pub manifest: EnvironmentManifest,
    pub manifest_sha256: String,
    pub production: bool,
}

impl ValidatedEnvironment {
    pub fn load(path: &Path) -> Result<Self, RunnerError> {
        let bytes =
            fs::read(path).map_err(|error| admission("environment_manifest_read", error))?;
        let value: serde_json::Value = parse_json_no_duplicates(&bytes)
            .map_err(|error| admission("environment_manifest_json", error))?;
        let production = value["schema"] == ENVIRONMENT_SCHEMA;
        let manifest: EnvironmentManifest = if production {
            serde_json::from_value(value)
                .map_err(|error| admission("environment_manifest_schema", error))?
        } else if value["schema"] == "pulsarmlx.f017.fixture-environment"
            && value["schema_version"] == 1
            && value["architecture"] == std::env::consts::ARCH
            && value["purpose"] == "checkpoint_free_ci"
        {
            fixture_manifest()
        } else {
            return Err(admission(
                "environment_manifest_schema",
                "unsupported or incomplete environment manifest",
            ));
        };
        if production {
            manifest.validate()?;
        }
        let manifest_sha256 =
            sha256_file(path).map_err(|error| admission("environment_manifest_hash", error))?;
        Ok(Self {
            manifest,
            manifest_sha256,
            production,
        })
    }

    pub fn public_platform(&self) -> BTreeMap<String, String> {
        let build = &self.manifest.build_environment;
        BTreeMap::from([
            ("architecture".to_owned(), build.architecture.clone()),
            ("macos_version".to_owned(), build.macos_version.clone()),
            ("macos_build".to_owned(), build.macos_build.clone()),
            ("xcode_version".to_owned(), build.xcode_version.clone()),
            ("sdk_version".to_owned(), build.sdk_version.clone()),
            ("metal_compiler".to_owned(), build.metal_compiler.clone()),
        ])
    }

    pub fn public_toolchain(&self) -> BTreeMap<String, String> {
        let build = &self.manifest.build_environment;
        BTreeMap::from([
            ("compiler".to_owned(), build.compiler.clone()),
            ("rustc".to_owned(), build.rustc.clone()),
            ("cargo".to_owned(), build.cargo.clone()),
            (
                "mlx_native_version".to_owned(),
                REQUIRED_MLX_VERSION.to_owned(),
            ),
            (
                "mlx_native_source_sha".to_owned(),
                REQUIRED_MLX_SOURCE_SHA.to_owned(),
            ),
            ("mlx_c_version".to_owned(), REQUIRED_MLXC_VERSION.to_owned()),
            (
                "mlx_c_source_sha".to_owned(),
                REQUIRED_MLXC_SOURCE_SHA.to_owned(),
            ),
        ])
    }

    pub fn verify_loaded_libraries(&self) -> Result<Vec<LoadedLibraryEvidence>, RunnerError> {
        if !self.production {
            return Ok(Vec::new());
        }
        verify_loaded_libraries(&self.manifest)
    }
}

fn fixture_manifest() -> EnvironmentManifest {
    EnvironmentManifest {
        schema: "pulsarmlx.f017.fixture-environment".to_owned(),
        schema_version: 1,
        classification: "CHECKPOINT_FREE_FIXTURE".to_owned(),
        build_environment: BuildEnvironment {
            architecture: std::env::consts::ARCH.to_owned(),
            macos_version: "not_applicable".to_owned(),
            macos_build: "not_applicable".to_owned(),
            xcode_version: "not_applicable".to_owned(),
            sdk_version: "not_applicable".to_owned(),
            metal_compiler: "not_applicable".to_owned(),
            compiler: "not_applicable".to_owned(),
            rustc: "fixture".to_owned(),
            cargo: "fixture".to_owned(),
        },
        pinned_installation: PinnedInstallation {
            prefix: PathBuf::from("fixture"),
            mlx: InstalledArtifact {
                version: REQUIRED_MLX_VERSION.to_owned(),
                source_sha: REQUIRED_MLX_SOURCE_SHA.to_owned(),
                library_sha256: "0".repeat(64),
                architecture: "arm64".to_owned(),
            },
            mlx_c: InstalledMlxC {
                version: REQUIRED_MLXC_VERSION.to_owned(),
                source_sha: REQUIRED_MLXC_SOURCE_SHA.to_owned(),
                library_sha256: "0".repeat(64),
                header_sha256: "0".repeat(64),
                architecture: "arm64".to_owned(),
            },
            linkage: LinkageEvidence {
                adapter_binary_links_mlxc: "not_applicable".to_owned(),
                adapter_binary_links_mlx: "not_applicable".to_owned(),
                mlxc_links_mlx: "not_applicable".to_owned(),
                isolated_prefix_selected: false,
                alternate_mlx_selected: false,
            },
        },
    }
}

impl EnvironmentManifest {
    fn validate(&self) -> Result<(), RunnerError> {
        if self.schema != ENVIRONMENT_SCHEMA || self.schema_version != ENVIRONMENT_SCHEMA_VERSION {
            return Err(admission(
                "environment_manifest_version",
                "unsupported environment manifest schema",
            ));
        }
        if self.classification != "READY FOR NEW SINGLE-P1 ADMISSION" {
            return Err(admission(
                "environment_manifest_classification",
                "environment is not admission-ready",
            ));
        }
        let build = &self.build_environment;
        if build.architecture != "arm64"
            || build.macos_version.is_empty()
            || build.macos_build.is_empty()
            || build.xcode_version.is_empty()
            || build.sdk_version.is_empty()
            || build.metal_compiler.is_empty()
            || build.compiler.is_empty()
            || build.rustc.is_empty()
            || build.cargo.is_empty()
        {
            return Err(admission(
                "environment_manifest_build",
                "required arm64 build identity is absent",
            ));
        }
        let install = &self.pinned_installation;
        validate_artifact(
            "mlx",
            &install.mlx.version,
            &install.mlx.source_sha,
            &install.mlx.library_sha256,
            &install.mlx.architecture,
            REQUIRED_MLX_VERSION,
            REQUIRED_MLX_SOURCE_SHA,
        )?;
        validate_artifact(
            "mlx_c",
            &install.mlx_c.version,
            &install.mlx_c.source_sha,
            &install.mlx_c.library_sha256,
            &install.mlx_c.architecture,
            REQUIRED_MLXC_VERSION,
            REQUIRED_MLXC_SOURCE_SHA,
        )?;
        require_sha("mlx_c_header", &install.mlx_c.header_sha256)?;
        if install
            .prefix
            .file_name()
            .and_then(|v| v.to_str())
            .is_none()
            || install.linkage.adapter_binary_links_mlxc != "@rpath/libmlxc.dylib"
            || install.linkage.adapter_binary_links_mlx != "@rpath/libmlx.dylib"
            || install.linkage.mlxc_links_mlx != "@rpath/libmlx.dylib"
            || !install.linkage.isolated_prefix_selected
            || install.linkage.alternate_mlx_selected
        {
            return Err(admission(
                "environment_manifest_linkage",
                "reviewed isolated linkage identity differs",
            ));
        }
        Ok(())
    }
}

fn validate_artifact(
    name: &str,
    version: &str,
    source_sha: &str,
    library_sha: &str,
    architecture: &str,
    required_version: &str,
    required_source_sha: &str,
) -> Result<(), RunnerError> {
    if version != required_version || source_sha != required_source_sha || architecture != "arm64" {
        return Err(admission(
            "environment_manifest_pin",
            format!("{name} reviewed pin differs"),
        ));
    }
    require_sha(name, library_sha)
}

fn require_sha(name: &str, value: &str) -> Result<(), RunnerError> {
    if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(admission(
            "environment_manifest_hash",
            format!("{name} SHA-256 is malformed"),
        ));
    }
    Ok(())
}

#[cfg(target_os = "macos")]
fn verify_loaded_libraries(
    manifest: &EnvironmentManifest,
) -> Result<Vec<LoadedLibraryEvidence>, RunnerError> {
    unsafe extern "C" {
        fn _dyld_image_count() -> u32;
        fn _dyld_get_image_name(image_index: u32) -> *const libc::c_char;
    }
    let mut matches: BTreeMap<&str, Vec<PathBuf>> =
        BTreeMap::from([("libmlx.dylib", Vec::new()), ("libmlxc.dylib", Vec::new())]);
    let count = unsafe { _dyld_image_count() };
    for index in 0..count {
        let raw = unsafe { _dyld_get_image_name(index) };
        if raw.is_null() {
            continue;
        }
        let path = PathBuf::from(unsafe { CStr::from_ptr(raw) }.to_string_lossy().as_ref());
        if let Some(name) = path.file_name().and_then(|value| value.to_str()) {
            if let Some(paths) = matches.get_mut(name) {
                paths.push(path);
            }
        }
    }
    let expected = [
        (
            "mlx_native",
            "libmlx.dylib",
            &manifest.pinned_installation.mlx.library_sha256,
        ),
        (
            "mlx_c",
            "libmlxc.dylib",
            &manifest.pinned_installation.mlx_c.library_sha256,
        ),
    ];
    expected
        .into_iter()
        .map(|(artifact, basename, expected_sha)| {
            let paths = &matches[basename];
            if paths.len() != 1 {
                return Err(admission(
                    "loaded_library_ambiguous",
                    format!(
                        "expected exactly one loaded {basename}, observed {}",
                        paths.len()
                    ),
                ));
            }
            let path = &paths[0];
            let actual_sha =
                sha256_file(path).map_err(|error| admission("loaded_library_hash", error))?;
            if &actual_sha != expected_sha {
                return Err(admission(
                    "loaded_library_mismatch",
                    format!("loaded {basename} hash differs"),
                ));
            }
            verify_arm64_macho(path)?;
            Ok(LoadedLibraryEvidence {
                artifact: artifact.to_owned(),
                resolved_basename: basename.to_owned(),
                actual_sha256: actual_sha,
                expected_sha256: expected_sha.clone(),
                architecture: "arm64".to_owned(),
            })
        })
        .collect()
}

#[cfg(not(target_os = "macos"))]
fn verify_loaded_libraries(
    _manifest: &EnvironmentManifest,
) -> Result<Vec<LoadedLibraryEvidence>, RunnerError> {
    Err(admission(
        "loaded_library_platform",
        "reviewed MLX libraries require macOS arm64",
    ))
}

#[cfg(target_os = "macos")]
fn verify_arm64_macho(path: &Path) -> Result<(), RunnerError> {
    let bytes = fs::read(path).map_err(|error| admission("loaded_library_read", error))?;
    if bytes.len() < 8 {
        return Err(admission(
            "loaded_library_architecture",
            "loaded library is not a Mach-O image",
        ));
    }
    let magic = u32::from_le_bytes(bytes[0..4].try_into().unwrap());
    let cpu = u32::from_le_bytes(bytes[4..8].try_into().unwrap());
    if magic != 0xfeedfacf || cpu != 0x0100000c {
        return Err(admission(
            "loaded_library_architecture",
            "loaded library is not a thin arm64 Mach-O image",
        ));
    }
    Ok(())
}

fn admission(code: &'static str, message: impl std::fmt::Display) -> RunnerError {
    RunnerError::new(
        FailureClass::AdmissionEnvironment,
        code,
        message.to_string(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_file(name: &str, bytes: &[u8]) -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path =
            std::env::temp_dir().join(format!("f017-env-{}-{suffix}-{name}", std::process::id()));
        fs::write(&path, bytes).unwrap();
        path
    }

    fn production_value() -> serde_json::Value {
        serde_json::json!({
            "schema": ENVIRONMENT_SCHEMA,
            "schema_version": 1,
            "classification": "READY FOR NEW SINGLE-P1 ADMISSION",
            "build_environment": {
                "architecture": "arm64", "macos_version": "26.0", "macos_build": "25A354",
                "xcode_version": "26.3", "sdk_version": "26.2", "metal_compiler": "metal",
                "compiler": "clang", "rustc": "rustc", "cargo": "cargo"
            },
            "pinned_installation": {
                "prefix": "/private/example/mlx-native-0.31.2-mlxc-0.6.0",
                "mlx": {"version": REQUIRED_MLX_VERSION, "source_sha": REQUIRED_MLX_SOURCE_SHA,
                    "library_sha256": "1".repeat(64), "architecture": "arm64"},
                "mlx_c": {"version": REQUIRED_MLXC_VERSION, "source_sha": REQUIRED_MLXC_SOURCE_SHA,
                    "library_sha256": "2".repeat(64), "header_sha256": "3".repeat(64), "architecture": "arm64"},
                "linkage": {"adapter_binary_links_mlxc": "@rpath/libmlxc.dylib",
                    "adapter_binary_links_mlx": "@rpath/libmlx.dylib", "mlxc_links_mlx": "@rpath/libmlx.dylib",
                    "isolated_prefix_selected": true, "alternate_mlx_selected": false}
            }
        })
    }

    fn load(value: &serde_json::Value) -> Result<ValidatedEnvironment, RunnerError> {
        let path = temp_file("manifest.json", &serde_json::to_vec(value).unwrap());
        let result = ValidatedEnvironment::load(&path);
        fs::remove_file(path).unwrap();
        result
    }

    #[test]
    fn production_manifest_requires_reviewed_schema_and_pins() {
        assert!(load(&production_value()).unwrap().production);
        assert!(load(&serde_json::json!({"schema": ENVIRONMENT_SCHEMA})).is_err());
        for (pointer, bad) in [
            ("/schema_version", serde_json::json!(2)),
            (
                "/build_environment/architecture",
                serde_json::json!("x86_64"),
            ),
            (
                "/pinned_installation/mlx/version",
                serde_json::json!("0.31.3"),
            ),
            (
                "/pinned_installation/mlx/source_sha",
                serde_json::json!("0".repeat(40)),
            ),
            (
                "/pinned_installation/mlx_c/library_sha256",
                serde_json::json!("bad"),
            ),
        ] {
            let mut value = production_value();
            *value.pointer_mut(pointer).unwrap() = bad;
            assert!(load(&value).is_err(), "accepted invalid {pointer}");
        }
    }

    #[test]
    fn fixture_manifest_is_explicit_and_narrow() {
        let valid = serde_json::json!({"schema":"pulsarmlx.f017.fixture-environment", "schema_version":1,
            "architecture":std::env::consts::ARCH, "purpose":"checkpoint_free_ci"});
        assert!(!load(&valid).unwrap().production);
        let mut invalid = valid;
        invalid["purpose"] = serde_json::json!("production");
        assert!(load(&invalid).is_err());
    }

    #[cfg(all(target_os = "macos", pulsar_native_mlx))]
    #[test]
    fn loaded_library_mismatch_is_rejected() {
        let environment = load(&production_value()).unwrap();
        let error = environment.verify_loaded_libraries().unwrap_err();
        assert!(matches!(
            error.code,
            "loaded_library_mismatch" | "loaded_library_ambiguous"
        ));
    }

    #[cfg(all(target_os = "macos", pulsar_native_mlx))]
    #[test]
    fn loaded_library_match_is_accepted() {
        unsafe extern "C" {
            fn _dyld_image_count() -> u32;
            fn _dyld_get_image_name(image_index: u32) -> *const libc::c_char;
        }
        let mut hashes = BTreeMap::new();
        for index in 0..unsafe { _dyld_image_count() } {
            let raw = unsafe { _dyld_get_image_name(index) };
            if raw.is_null() {
                continue;
            }
            let path = PathBuf::from(unsafe { CStr::from_ptr(raw) }.to_string_lossy().as_ref());
            if let Some(name @ ("libmlx.dylib" | "libmlxc.dylib")) =
                path.file_name().and_then(|value| value.to_str())
            {
                hashes.insert(name.to_owned(), sha256_file(&path).unwrap());
            }
        }
        let mut value = production_value();
        value["pinned_installation"]["mlx"]["library_sha256"] =
            serde_json::json!(hashes["libmlx.dylib"]);
        value["pinned_installation"]["mlx_c"]["library_sha256"] =
            serde_json::json!(hashes["libmlxc.dylib"]);
        let environment = load(&value).unwrap();
        let libraries = environment.verify_loaded_libraries().unwrap();
        assert_eq!(libraries.len(), 2);
        assert!(libraries
            .iter()
            .all(|library| library.actual_sha256 == library.expected_sha256));
    }
}
