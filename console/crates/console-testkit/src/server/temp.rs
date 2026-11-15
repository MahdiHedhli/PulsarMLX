//! A temporary folder removed on drop, for configuration folders and process scratch.
//!
//! The kit adds no third-party crate for it: the folder is a fresh directory under the
//! system temporary folder (`TMPDIR` on Unix), named from a prefix, the process id, a
//! counter and the clock, and created with `create_dir` so two tests never share one.

use std::io;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

/// How many names are tried before giving up.
const ATTEMPTS: u32 = 64;

static NEXT: AtomicU64 = AtomicU64::new(0);

/// A directory that is removed, with everything in it, when this value is dropped.
#[derive(Debug)]
pub struct TempDir {
    path: PathBuf,
    keep: bool,
}

impl TempDir {
    /// Makes a new, empty directory under the system temporary folder. `prefix` keeps only
    /// ASCII letters, digits, `-` and `_`.
    pub fn new(prefix: &str) -> io::Result<Self> {
        Self::new_in(&std::env::temp_dir(), prefix)
    }

    /// Makes a new, empty directory under `parent`.
    pub fn new_in(parent: &Path, prefix: &str) -> io::Result<Self> {
        let clean: String = prefix
            .chars()
            .filter(|c| c.is_ascii_alphanumeric() || *c == '-' || *c == '_')
            .take(32)
            .collect();
        let mut last = None;
        for _ in 0..ATTEMPTS {
            let n = NEXT.fetch_add(1, Ordering::Relaxed);
            let nanos = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_or(0, |d| d.subsec_nanos());
            let name = format!(
                "pulsar-console-testkit-{clean}-{}-{n}-{nanos}",
                std::process::id()
            );
            let path = parent.join(name);
            match std::fs::create_dir(&path) {
                Ok(()) => return Ok(Self { path, keep: false }),
                Err(e) if e.kind() == io::ErrorKind::AlreadyExists => last = Some(e),
                Err(e) => return Err(e),
            }
        }
        Err(last.unwrap_or_else(|| io::Error::other("no free temporary name")))
    }

    /// The directory.
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Keeps the directory after the drop (to look at it after a failure), and returns
    /// its path.
    pub fn keep(mut self) -> PathBuf {
        self.keep = true;
        self.path.clone()
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        if !self.keep {
            let _ = std::fs::remove_dir_all(&self.path);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn made_fresh_and_removed_on_drop() {
        let a = TempDir::new("unit/../x").expect("temp dir");
        let b = TempDir::new("unit").expect("temp dir");
        assert_ne!(a.path(), b.path());
        assert!(a.path().is_dir());
        let name = a.path().file_name().and_then(|n| n.to_str()).unwrap_or("");
        assert!(name.starts_with("pulsar-console-testkit-unitx-"), "{name}");
        std::fs::write(a.path().join("f"), b"x").expect("write");
        let path = a.path().to_path_buf();
        drop(a);
        assert!(!path.exists());
        let kept = b.keep();
        assert!(kept.is_dir());
        std::fs::remove_dir_all(kept).expect("cleanup");
    }
}
