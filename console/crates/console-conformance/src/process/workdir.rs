//! The per-run directory: `HOME`, the `XDG_*` directories, `TMPDIR`, the data directory
//! and the captured output of one process.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use super::ProcessError;

static NEXT: AtomicU64 = AtomicU64::new(0);

/// The most attempts at a fresh directory name.
const MAX_ATTEMPTS: u32 = 64;

/// A fresh directory for one run, with this layout:
///
/// ```text
/// <root>/home      HOME; .config, .local/share, .cache, .local/state below it
/// <root>/tmp       TMPDIR
/// <root>/run       XDG_RUNTIME_DIR (mode 0700)
/// <root>/data      the data directory and the working directory of the process
/// <root>/stdout.txt, <root>/stderr.txt   the captured output
/// ```
///
/// A directory the harness created is removed when the value is dropped, unless
/// [`Workdir::keep`] was called; the harness calls it when a run fails, so CI can keep
/// the captured output as an artifact.
#[derive(Debug)]
pub struct Workdir {
    root: PathBuf,
    remove_on_drop: bool,
}

impl Workdir {
    /// Creates a fresh directory under `parent` (the system temporary directory when
    /// `None`), named `cnf-<pid>-<n>-<nanos>`.
    pub fn create(parent: Option<&Path>) -> Result<Self, ProcessError> {
        let parent = parent.map_or_else(std::env::temp_dir, Path::to_path_buf);
        fs::create_dir_all(&parent)
            .map_err(|e| ProcessError::io(format!("create {}", parent.display()), e))?;
        let mut last = None;
        for _ in 0..MAX_ATTEMPTS {
            let nanos = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map(|d| d.subsec_nanos())
                .unwrap_or(0);
            let n = NEXT.fetch_add(1, Ordering::Relaxed);
            let root = parent.join(format!("cnf-{}-{n}-{nanos}", std::process::id()));
            match fs::create_dir(&root) {
                Ok(()) => {
                    let dir = Workdir {
                        root,
                        remove_on_drop: true,
                    };
                    dir.lay_out()?;
                    return Ok(dir);
                }
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => last = Some(e),
                Err(e) => return Err(ProcessError::io(format!("create {}", root.display()), e)),
            }
        }
        Err(ProcessError::io(
            "find a fresh run directory",
            last.unwrap_or_else(|| std::io::Error::other("too many attempts")),
        ))
    }

    /// Uses `root`, which must be missing or empty; it is created and never removed by
    /// the harness.
    pub fn at(root: &Path) -> Result<Self, ProcessError> {
        if root.exists() {
            let mut entries = fs::read_dir(root)
                .map_err(|e| ProcessError::io(format!("read {}", root.display()), e))?;
            if entries.next().is_some() {
                return Err(ProcessError::WorkdirTaken {
                    path: root.to_path_buf(),
                });
            }
        }
        fs::create_dir_all(root)
            .map_err(|e| ProcessError::io(format!("create {}", root.display()), e))?;
        let dir = Workdir {
            root: root.to_path_buf(),
            remove_on_drop: false,
        };
        dir.lay_out()?;
        Ok(dir)
    }

    fn lay_out(&self) -> Result<(), ProcessError> {
        for sub in [
            "home/.config",
            "home/.local/share",
            "home/.local/state",
            "home/.cache",
            "tmp",
            "run",
            "data",
        ] {
            let p = self.root.join(sub);
            fs::create_dir_all(&p)
                .map_err(|e| ProcessError::io(format!("create {}", p.display()), e))?;
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let run = self.runtime();
            fs::set_permissions(&run, fs::Permissions::from_mode(0o700))
                .map_err(|e| ProcessError::io(format!("chmod {}", run.display()), e))?;
        }
        Ok(())
    }

    /// The directory itself.
    pub fn root(&self) -> &Path {
        &self.root
    }

    /// `HOME`.
    pub fn home(&self) -> PathBuf {
        self.root.join("home")
    }

    /// `TMPDIR`.
    pub fn tmp(&self) -> PathBuf {
        self.root.join("tmp")
    }

    /// `XDG_RUNTIME_DIR`.
    pub fn runtime(&self) -> PathBuf {
        self.root.join("run")
    }

    /// The data directory, also the process's working directory.
    pub fn data(&self) -> PathBuf {
        self.root.join("data")
    }

    /// The captured standard output.
    pub fn stdout_path(&self) -> PathBuf {
        self.root.join("stdout.txt")
    }

    /// The captured standard error.
    pub fn stderr_path(&self) -> PathBuf {
        self.root.join("stderr.txt")
    }

    /// Keeps the directory when the value is dropped.
    pub fn keep(&mut self) {
        self.remove_on_drop = false;
    }

    /// Whether the directory is removed on drop.
    pub fn removed_on_drop(&self) -> bool {
        self.remove_on_drop
    }
}

impl Drop for Workdir {
    fn drop(&mut self) {
        if self.remove_on_drop {
            let _ = fs::remove_dir_all(&self.root);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_fresh_directory_with_its_layout_is_removed_on_drop() {
        let a = Workdir::create(None).unwrap();
        let b = Workdir::create(None).unwrap();
        assert_ne!(a.root(), b.root());
        for p in [
            a.home(),
            a.tmp(),
            a.runtime(),
            a.data(),
            a.home().join(".cache"),
        ] {
            assert!(p.is_dir(), "{}", p.display());
        }
        let root = a.root().to_path_buf();
        drop(a);
        assert!(!root.exists());
        let mut kept = b;
        kept.keep();
        let root = kept.root().to_path_buf();
        drop(kept);
        assert!(root.exists());
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn at_refuses_a_directory_in_use() {
        let parent = Workdir::create(None).unwrap();
        let taken = parent.root().join("data");
        fs::write(taken.join("x"), "y").unwrap();
        assert!(matches!(
            Workdir::at(&taken),
            Err(ProcessError::WorkdirTaken { .. })
        ));
        let fresh = parent.root().join("fresh");
        let w = Workdir::at(&fresh).unwrap();
        assert!(w.data().is_dir() && !w.removed_on_drop());
    }
}
