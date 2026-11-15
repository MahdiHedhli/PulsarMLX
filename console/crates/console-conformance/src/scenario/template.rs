//! Chat-template references and their resolution.
//!
//! A scenario names its chat template in one of two ways:
//!
//! - a project-authored template: a plain name such as `chatml-synthetic`, resolved as
//!   `<templates dir>/<name>.jinja` in the PulsarMLX tree;
//! - `vendor:<path>`: a vendor template read at test time from the hash-verified pinned
//!   donor checkout named by `PULSAR_CONSOLE_VENDOR_DIR` (naming.md section 3.10), for
//!   example `vendor:serve/chat_template.jinja`. No vendor template is ever committed
//!   (deviation LIC-1.1); its text is read only where it is lawfully present and only its
//!   SHA-256 is compared (LIC-1.4). Without the variable a vendor reference resolves to
//!   [`VendorResolution::Skipped`], which callers must report as skipped, never passed. A
//!   hash mismatch is a hard failure, never a skip.

use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};

/// The environment variable that names the pinned vendor checkout.
pub const VENDOR_DIR_ENV: &str = "PULSAR_CONSOLE_VENDOR_DIR";

/// The largest template file read, in bytes.
pub const MAX_TEMPLATE_BYTES: u64 = 4 * 1024 * 1024;

/// The longest template name or vendor path, in characters.
pub const MAX_TEMPLATE_REF_CHARS: usize = 256;

/// A scenario's chat-template reference.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TemplateRef {
    /// A project-authored template, by name.
    Project(String),
    /// A vendor template, by its path inside the pinned donor checkout.
    Vendor(String),
}

/// Why a template could not be resolved.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TemplateError {
    /// The template file does not exist or is not a regular file.
    NotFound(PathBuf),
    /// The resolved file lies outside the directory it was resolved in (a symbolic link
    /// that leaves it).
    OutsideRoot(PathBuf),
    /// The file is larger than [`MAX_TEMPLATE_BYTES`].
    TooLarge(PathBuf),
    /// The expected digest given by the caller is not 64 lower-case hexadecimal digits.
    BadExpectedDigest,
    /// The file's SHA-256 is not the expected one.
    HashMismatch {
        /// The file read.
        path: PathBuf,
        /// The digest the pin manifest expects.
        expected: String,
        /// The digest of the file.
        actual: String,
    },
    /// Reading failed.
    Io {
        /// The file.
        path: PathBuf,
        /// The operating system's description.
        message: String,
    },
    /// The reference is of the other kind than the resolver called.
    WrongKind,
}

impl std::fmt::Display for TemplateError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            TemplateError::NotFound(p) => write!(f, "template not found: {}", p.display()),
            TemplateError::OutsideRoot(p) => {
                write!(
                    f,
                    "template resolves outside its directory: {}",
                    p.display()
                )
            }
            TemplateError::TooLarge(p) => write!(
                f,
                "template larger than {MAX_TEMPLATE_BYTES} bytes: {}",
                p.display()
            ),
            TemplateError::BadExpectedDigest => {
                write!(f, "the expected SHA-256 is not 64 lower-case hex digits")
            }
            TemplateError::HashMismatch {
                path,
                expected,
                actual,
            } => write!(
                f,
                "vendor template hash mismatch for {}: expected {expected}, found {actual}",
                path.display()
            ),
            TemplateError::Io { path, message } => {
                write!(f, "cannot read {}: {message}", path.display())
            }
            TemplateError::WrongKind => write!(f, "template reference of the other kind"),
        }
    }
}

impl std::error::Error for TemplateError {}

/// A vendor template read and verified.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VendorTemplate {
    /// The file that was read.
    pub path: PathBuf,
    /// Its SHA-256, lower-case hex.
    pub sha256: String,
    /// Its text. Never written into the repository or into a record (LIC-1.4).
    pub text: String,
}

/// The outcome of resolving a vendor reference.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum VendorResolution {
    /// The vendor checkout is not configured: the scenario reports skipped.
    Skipped,
    /// The template was found and its hash matched.
    Verified(VendorTemplate),
}

impl TemplateRef {
    /// The reference as a scenario writes it.
    pub fn as_written(&self) -> String {
        match self {
            TemplateRef::Project(name) => name.clone(),
            TemplateRef::Vendor(path) => format!("vendor:{path}"),
        }
    }

    /// Resolves a project-authored reference to `<templates_dir>/<name>.jinja`.
    pub fn resolve_project(&self, templates_dir: &Path) -> Result<PathBuf, TemplateError> {
        let TemplateRef::Project(name) = self else {
            return Err(TemplateError::WrongKind);
        };
        let path = templates_dir.join(format!("{name}.jinja"));
        regular_file_inside(templates_dir, &path)?;
        Ok(path)
    }

    /// Resolves a vendor reference against `vendor_dir` (normally the value of
    /// [`VENDOR_DIR_ENV`]; `None` when it is unset) and checks the file's SHA-256 against
    /// `expected_sha256`, the lower-case hex digest from the pin manifest.
    pub fn resolve_vendor(
        &self,
        vendor_dir: Option<&Path>,
        expected_sha256: &str,
    ) -> Result<VendorResolution, TemplateError> {
        let TemplateRef::Vendor(rel) = self else {
            return Err(TemplateError::WrongKind);
        };
        if expected_sha256.len() != 64
            || !expected_sha256
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            return Err(TemplateError::BadExpectedDigest);
        }
        let Some(root) = vendor_dir else {
            return Ok(VendorResolution::Skipped);
        };
        let path = root.join(rel);
        regular_file_inside(root, &path)?;
        let text = read_bounded(&path)?;
        let sha256 = hex(&Sha256::digest(text.as_bytes()));
        if sha256 != expected_sha256 {
            return Err(TemplateError::HashMismatch {
                path,
                expected: expected_sha256.to_string(),
                actual: sha256,
            });
        }
        Ok(VendorResolution::Verified(VendorTemplate {
            path,
            sha256,
            text,
        }))
    }
}

/// The vendor checkout named by [`VENDOR_DIR_ENV`], or `None` when unset or empty.
pub fn vendor_dir_from_env() -> Option<PathBuf> {
    match std::env::var_os(VENDOR_DIR_ENV) {
        Some(v) if !v.is_empty() => Some(PathBuf::from(v)),
        _ => None,
    }
}

fn regular_file_inside(root: &Path, path: &Path) -> Result<(), TemplateError> {
    let io = |e: std::io::Error| TemplateError::Io {
        path: path.to_path_buf(),
        message: e.to_string(),
    };
    let meta = match fs::metadata(path) {
        Ok(m) => m,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            return Err(TemplateError::NotFound(path.to_path_buf()))
        }
        Err(e) => return Err(io(e)),
    };
    if !meta.is_file() {
        return Err(TemplateError::NotFound(path.to_path_buf()));
    }
    let real_root = fs::canonicalize(root).map_err(io)?;
    let real = fs::canonicalize(path).map_err(io)?;
    if !real.starts_with(&real_root) {
        return Err(TemplateError::OutsideRoot(path.to_path_buf()));
    }
    Ok(())
}

fn read_bounded(path: &Path) -> Result<String, TemplateError> {
    let io = |e: std::io::Error| TemplateError::Io {
        path: path.to_path_buf(),
        message: e.to_string(),
    };
    let file = fs::File::open(path).map_err(io)?;
    let mut buf = Vec::new();
    file.take(MAX_TEMPLATE_BYTES + 1)
        .read_to_end(&mut buf)
        .map_err(io)?;
    if buf.len() as u64 > MAX_TEMPLATE_BYTES {
        return Err(TemplateError::TooLarge(path.to_path_buf()));
    }
    String::from_utf8(buf).map_err(|e| TemplateError::Io {
        path: path.to_path_buf(),
        message: e.to_string(),
    })
}

/// Lower-case hex of `bytes`.
pub(crate) fn hex(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        for nibble in [b >> 4, b & 0x0f] {
            out.push(char::from_digit(u32::from(nibble), 16).unwrap_or('0'));
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch(name: &str) -> PathBuf {
        let dir =
            std::env::temp_dir().join(format!("cnf02-template-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn project_template_resolves_to_a_jinja_file() {
        let dir = scratch("project");
        fs::write(dir.join("chatml-synthetic.jinja"), "{{ x }}").unwrap();
        let r = TemplateRef::Project("chatml-synthetic".into());
        assert_eq!(
            r.resolve_project(&dir).unwrap(),
            dir.join("chatml-synthetic.jinja")
        );
        let missing = TemplateRef::Project("absent".into());
        assert!(matches!(
            missing.resolve_project(&dir),
            Err(TemplateError::NotFound(_))
        ));
        assert_eq!(
            r.resolve_vendor(Some(&dir), &"0".repeat(64)),
            Err(TemplateError::WrongKind)
        );
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn vendor_template_is_skipped_without_a_checkout() {
        let r = TemplateRef::Vendor("serve/chat_template.jinja".into());
        assert_eq!(
            r.resolve_vendor(None, &"a".repeat(64)),
            Ok(VendorResolution::Skipped)
        );
    }

    #[test]
    fn vendor_template_hash_is_checked() {
        let dir = scratch("vendor");
        fs::create_dir_all(dir.join("serve")).unwrap();
        fs::write(dir.join("serve/t.jinja"), "abc").unwrap();
        let r = TemplateRef::Vendor("serve/t.jinja".into());
        // SHA-256 of "abc"
        let good = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
        match r.resolve_vendor(Some(&dir), good).unwrap() {
            VendorResolution::Verified(t) => {
                assert_eq!(t.sha256, good);
                assert_eq!(t.text, "abc");
            }
            other => panic!("unexpected {other:?}"),
        }
        let bad = "0".repeat(64);
        assert!(matches!(
            r.resolve_vendor(Some(&dir), &bad),
            Err(TemplateError::HashMismatch { .. })
        ));
        assert_eq!(
            r.resolve_vendor(Some(&dir), "ABC"),
            Err(TemplateError::BadExpectedDigest)
        );
        let absent = TemplateRef::Vendor("serve/none.jinja".into());
        assert!(matches!(
            absent.resolve_vendor(Some(&dir), good),
            Err(TemplateError::NotFound(_))
        ));
        fs::remove_dir_all(&dir).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn a_link_leaving_the_checkout_is_refused() {
        let dir = scratch("escape");
        let outside = scratch("escape-target");
        fs::write(outside.join("t.jinja"), "abc").unwrap();
        std::os::unix::fs::symlink(outside.join("t.jinja"), dir.join("t.jinja")).unwrap();
        let r = TemplateRef::Vendor("t.jinja".into());
        assert!(matches!(
            r.resolve_vendor(Some(&dir), &"0".repeat(64)),
            Err(TemplateError::OutsideRoot(_))
        ));
        fs::remove_dir_all(&dir).unwrap();
        fs::remove_dir_all(&outside).unwrap();
    }

    #[test]
    fn hex_is_lower_case() {
        assert_eq!(hex(&[0x00, 0xab, 0xff]), "00abff");
    }
}
