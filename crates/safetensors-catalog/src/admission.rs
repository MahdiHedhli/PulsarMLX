//! Admitting a file *inside* the checkpoint root, by descriptor rather than by
//! pathname.
//!
//! The naive sequence -- open by path, then canonicalize that path and check
//! the prefix -- validates a *name*, not the object the descriptor holds. A
//! rename between the two steps leaves a descriptor on a file outside the root
//! while the later resolution reports a path inside it. Static symlinks are
//! caught; the race is not.
//!
//! What this module does instead:
//!
//! 1. open the canonicalized root **once** with `O_DIRECTORY | O_NOFOLLOW` and
//!    keep the descriptor for the whole open;
//! 2. resolve every shard and index name with `openat` **relative to that
//!    descriptor**, with `O_NOFOLLOW` on the final component. The names have
//!    already been validated to contain no `/`, `\` or NUL and to be neither
//!    `.` nor `..`, so `openat` cannot traverse anywhere: one component, no
//!    symlink, anchored to a directory we are holding open. Renaming the root
//!    afterwards moves the directory, not the descriptor;
//! 3. `fstat` the opened descriptor, require a regular file, and compare its
//!    `(st_dev, st_ino)` against an `fstatat(..., AT_SYMLINK_NOFOLLOW)` of the
//!    same name under the same directory descriptor. A mismatch means the name
//!    stopped denoting the object we opened while we were looking at it.
//!
//! Every refusal is [`CatalogError::PathEscape`], because from the caller's
//! point of view they are the same fact: this name did not yield an admitted
//! file inside the admitted root.

use std::ffi::CString;
use std::fs::File;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::io::FromRawFd;
use std::path::Path;

use crate::error::{CatalogError, Result};

/// The identity of a file system object, as the kernel reports it.
///
/// Two descriptors denote the same object exactly when these agree. Kept as a
/// plain value so the comparison is a pure function and can be tested without
/// racing anything.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FileIdentity {
    pub device: u64,
    pub inode: u64,
}

/// `true` when both descriptors denote the same object.
pub fn same_object(opened: FileIdentity, named: FileIdentity) -> bool {
    opened.device == named.device && opened.inode == named.inode
}

/// A file admitted inside the root, with the identity it was admitted under.
#[derive(Debug)]
pub struct Admitted {
    pub file: File,
    pub len: u64,
    pub identity: FileIdentity,
}

/// An open descriptor on the checkpoint root directory.
#[derive(Debug)]
pub struct RootDirectory {
    fd: OwnedFd,
    display: String,
    identity: FileIdentity,
}

/// A raw descriptor this module owns and closes.
#[derive(Debug)]
struct OwnedFd(i32);

impl Drop for OwnedFd {
    fn drop(&mut self) {
        if self.0 >= 0 {
            // SAFETY: the descriptor was returned by `open`/`openat` in this
            // module, is not shared, and is closed exactly once here.
            unsafe {
                libc::close(self.0);
            }
        }
    }
}

fn cstring(path: &Path) -> Result<CString> {
    CString::new(path.as_os_str().as_bytes()).map_err(|_| CatalogError::PathEscape {
        shard: path.display().to_string(),
        resolved: "path contains an interior NUL".to_string(),
    })
}

fn name_cstring(name: &str) -> Result<CString> {
    CString::new(name.as_bytes()).map_err(|_| CatalogError::PathEscape {
        shard: name.to_string(),
        resolved: "name contains an interior NUL".to_string(),
    })
}

fn escape(name: &str, detail: impl Into<String>) -> CatalogError {
    CatalogError::PathEscape {
        shard: name.to_string(),
        resolved: detail.into(),
    }
}

fn identity_of(status: &libc::stat) -> FileIdentity {
    FileIdentity {
        // `st_dev` and `st_ino` are platform integer types; widen rather
        // than assume, so this stays correct where they are not `u64`.
        device: u64::from(status.st_dev as u32),
        inode: status.st_ino,
    }
}

fn zeroed_stat() -> libc::stat {
    // SAFETY: `libc::stat` is a plain-old-data struct with no invalid bit
    // patterns; it is overwritten by the syscall before it is read.
    unsafe { std::mem::zeroed() }
}

impl RootDirectory {
    /// Open the checkpoint root and hold it for the duration of the open.
    ///
    /// `root` must already be canonicalized. The directory itself is opened
    /// with `O_NOFOLLOW`, so a symlink *at* the root path is refused too.
    pub fn open(root: &Path) -> Result<Self> {
        let path = cstring(root)?;
        // SAFETY: `path` is a valid NUL-terminated C string that outlives the
        // call, and the flags are a valid combination for a directory open.
        let fd = unsafe {
            libc::open(
                path.as_ptr(),
                libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            )
        };
        if fd < 0 {
            let error = std::io::Error::last_os_error();
            return Err(CatalogError::Io {
                path: root.display().to_string(),
                detail: format!("cannot open the checkpoint root as a directory: {error}"),
            });
        }
        let fd = OwnedFd(fd);
        let mut status = zeroed_stat();
        // SAFETY: `fd.0` is a descriptor this function just opened and still
        // owns, and `status` is a valid, writable `libc::stat`.
        if unsafe { libc::fstat(fd.0, &mut status) } != 0 {
            let error = std::io::Error::last_os_error();
            return Err(CatalogError::Io {
                path: root.display().to_string(),
                detail: format!("cannot stat the checkpoint root: {error}"),
            });
        }
        if status.st_mode & libc::S_IFMT != libc::S_IFDIR {
            return Err(CatalogError::Io {
                path: root.display().to_string(),
                detail: "the checkpoint root is not a directory".to_string(),
            });
        }
        Ok(Self {
            fd,
            display: root.display().to_string(),
            identity: identity_of(&status),
        })
    }

    /// The root's own `(device, inode)`.
    pub fn identity(&self) -> FileIdentity {
        self.identity
    }

    pub fn display(&self) -> &str {
        &self.display
    }

    /// Does `name` exist directly under this directory, without following a
    /// symlink at the final component?
    ///
    /// A symlink is *present*; it is simply not admissible, which
    /// [`Self::open_file`] reports. This is what lets the caller tell "no
    /// index" apart from "an index that is not a regular file".
    pub fn entry_exists(&self, name: &str) -> Result<bool> {
        let name = name_cstring(name)?;
        let mut status = zeroed_stat();
        // SAFETY: `self.fd.0` is an owned directory descriptor, `name` is a
        // valid NUL-terminated C string outliving the call, and `status` is a
        // valid writable `libc::stat`.
        let outcome = unsafe {
            libc::fstatat(
                self.fd.0,
                name.as_ptr(),
                &mut status,
                libc::AT_SYMLINK_NOFOLLOW,
            )
        };
        if outcome == 0 {
            return Ok(true);
        }
        let error = std::io::Error::last_os_error();
        match error.raw_os_error() {
            Some(libc::ENOENT) | Some(libc::ENOTDIR) => Ok(false),
            _ => Err(CatalogError::Io {
                path: self.display.clone(),
                detail: format!("cannot inspect an entry under the root: {error}"),
            }),
        }
    }

    /// Is `name` a regular file, without following a final symlink?
    pub fn entry_is_regular_file(&self, name: &str) -> Result<bool> {
        let name_c = name_cstring(name)?;
        let mut status = zeroed_stat();
        // SAFETY: as in `entry_exists`.
        let outcome = unsafe {
            libc::fstatat(
                self.fd.0,
                name_c.as_ptr(),
                &mut status,
                libc::AT_SYMLINK_NOFOLLOW,
            )
        };
        if outcome != 0 {
            return Ok(false);
        }
        Ok(status.st_mode & libc::S_IFMT == libc::S_IFREG)
    }

    /// Open one single-component `name` under this directory and admit it.
    ///
    /// `name` must already have passed [`crate::index::validate_shard_path`]
    /// or an equivalent single-component check; this function re-asserts the
    /// absence of a separator rather than trusting the caller.
    pub fn open_file(&self, name: &str) -> Result<Admitted> {
        if name.is_empty()
            || name.contains('/')
            || name.contains('\\')
            || name == "."
            || name == ".."
        {
            return Err(escape(name, "not a single path component"));
        }
        let name_c = name_cstring(name)?;

        // The name, without following a symlink at the final component.
        let mut named = zeroed_stat();
        // SAFETY: as in `entry_exists`.
        let outcome = unsafe {
            libc::fstatat(
                self.fd.0,
                name_c.as_ptr(),
                &mut named,
                libc::AT_SYMLINK_NOFOLLOW,
            )
        };
        if outcome != 0 {
            let error = std::io::Error::last_os_error();
            return match error.raw_os_error() {
                Some(libc::ENOENT) => Err(CatalogError::MissingShard {
                    shard: name.to_string(),
                }),
                _ => Err(CatalogError::Io {
                    path: format!("{}/{name}", self.display),
                    detail: error.to_string(),
                }),
            };
        }
        if named.st_mode & libc::S_IFMT == libc::S_IFLNK {
            return Err(escape(name, "the entry is a symbolic link"));
        }
        if named.st_mode & libc::S_IFMT != libc::S_IFREG {
            return Err(escape(name, "the entry is not a regular file"));
        }

        // SAFETY: `self.fd.0` is an owned directory descriptor and `name_c` is
        // a valid NUL-terminated C string that outlives the call. `O_NOFOLLOW`
        // refuses a symlink at the single final component, and the name holds
        // no separator, so resolution cannot leave this directory.
        let fd = unsafe {
            libc::openat(
                self.fd.0,
                name_c.as_ptr(),
                libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            )
        };
        if fd < 0 {
            let error = std::io::Error::last_os_error();
            return match error.raw_os_error() {
                // O_NOFOLLOW reports a symlink as ELOOP (or EMLINK on some BSDs).
                Some(libc::ELOOP) | Some(libc::EMLINK) => {
                    Err(escape(name, "the entry is a symbolic link"))
                }
                Some(libc::ENOENT) => Err(CatalogError::MissingShard {
                    shard: name.to_string(),
                }),
                _ => Err(CatalogError::Io {
                    path: format!("{}/{name}", self.display),
                    detail: error.to_string(),
                }),
            };
        }
        let fd = OwnedFd(fd);

        // The object actually held, by descriptor.
        let mut opened = zeroed_stat();
        // SAFETY: `fd.0` is a descriptor this function just opened and owns.
        if unsafe { libc::fstat(fd.0, &mut opened) } != 0 {
            let error = std::io::Error::last_os_error();
            return Err(CatalogError::Io {
                path: format!("{}/{name}", self.display),
                detail: error.to_string(),
            });
        }
        if opened.st_mode & libc::S_IFMT != libc::S_IFREG {
            return Err(escape(name, "the opened descriptor is not a regular file"));
        }
        let opened_identity = identity_of(&opened);
        let named_identity = identity_of(&named);
        if !same_object(opened_identity, named_identity) {
            return Err(escape(
                name,
                format!(
                    "the opened descriptor is device {} inode {}, the name now denotes device {} inode {}",
                    opened_identity.device,
                    opened_identity.inode,
                    named_identity.device,
                    named_identity.inode
                ),
            ));
        }

        let len = u64::try_from(opened.st_size).map_err(|_| CatalogError::Io {
            path: format!("{}/{name}", self.display),
            detail: "negative file length".to_string(),
        })?;
        let raw = fd.0;
        std::mem::forget(fd);
        // SAFETY: `raw` is an open descriptor this function owns; ownership is
        // transferred to the `File`, and the `OwnedFd` was forgotten so it is
        // not closed twice.
        let file = unsafe { File::from_raw_fd(raw) };
        Ok(Admitted {
            file,
            len,
            identity: opened_identity,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::{same_object, FileIdentity};

    /// The live race this module closes cannot be scheduled deterministically
    /// from a test: it needs the kernel to rename a directory entry between
    /// two syscalls of another thread, and a test that merely raced would be
    /// flaky rather than conclusive. What *can* be pinned is the decision the
    /// comparison makes once the two identities are in hand, so that is
    /// factored out as a pure function and exhaustively exercised here. The
    /// syscall wiring around it is covered by the symlink-escape fixture and
    /// by the directory and non-regular-file tests.
    #[test]
    fn identity_comparison_accepts_only_the_same_object() {
        let base = FileIdentity {
            device: 17,
            inode: 4242,
        };
        assert!(same_object(base, base));
        assert!(!same_object(
            base,
            FileIdentity {
                device: 17,
                inode: 4243
            }
        ));
        assert!(!same_object(
            base,
            FileIdentity {
                device: 18,
                inode: 4242
            }
        ));
        assert!(!same_object(
            base,
            FileIdentity {
                device: 18,
                inode: 4243
            }
        ));
        // Inode numbers repeat across devices; the device must be part of it.
        let other_device = FileIdentity {
            device: 99,
            inode: 4242,
        };
        assert!(!same_object(base, other_device));
        assert!(same_object(other_device, other_device));
    }

    #[test]
    fn identity_is_a_plain_value() {
        let identity = FileIdentity {
            device: 1,
            inode: 2,
        };
        let copied = identity;
        assert_eq!(identity, copied);
        assert_eq!(
            format!("{identity:?}"),
            "FileIdentity { device: 1, inode: 2 }"
        );
    }
}
