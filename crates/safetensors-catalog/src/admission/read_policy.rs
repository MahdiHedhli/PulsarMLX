//! One cache-policy request per newly opened file description.
use super::RootDirectory;
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::fs::File;
use std::io;
use std::os::unix::fs::{FileExt, MetadataExt};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum Policy {
    BufferedRequested,
    NoCacheRequested,
}
impl Policy {
    pub fn argument(self) -> i32 {
        match self {
            Self::BufferedRequested => 0,
            Self::NoCacheRequested => 1,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct Stamp {
    dev: u64,
    ino: u64,
    len: u64,
    modified: [i64; 2],
    changed: [i64; 2],
}
impl Stamp {
    fn read(file: &File) -> io::Result<Self> {
        let m = file.metadata()?;
        if !m.is_file() {
            return Err(io::ErrorKind::InvalidData.into());
        }
        Ok(Self {
            dev: m.dev(),
            ino: m.ino(),
            len: m.len(),
            modified: [m.mtime(), m.mtime_nsec()],
            changed: [m.ctime(), m.ctime_nsec()],
        })
    }
    fn digest(self) -> [u8; 32] {
        let mut h = Sha256::new();
        h.update(b"buffered-window-descriptor/1");
        for n in [self.dev, self.ino, self.len] {
            h.update(n.to_le_bytes());
        }
        for n in self.modified.into_iter().chain(self.changed) {
            h.update(n.to_le_bytes());
        }
        h.finalize().into()
    }
}

#[derive(Clone, Copy, Debug, Serialize)]
pub struct Setter {
    pub command: &'static str,
    pub number: i32,
    pub argument: i32,
    pub returned: i32,
    pub errno: Option<i32>,
}
#[derive(Clone, Copy, Debug, Default, Serialize)]
pub struct Setup {
    pub open_attempted: bool,
    pub fresh_owned: bool,
    pub original_stamp: Option<[u8; 32]>,
    pub fresh_stamp: Option<[u8; 32]>,
    pub matched: Option<bool>,
    pub setter: Option<Setter>,
    pub configured: bool,
}
#[derive(Debug)]
pub struct SetupFailure {
    pub reason: &'static str,
    pub observation: Setup,
}

/// The file is owned exclusively. The safe surface exposes neither the file nor a policy setter.
pub struct FixedDescriptor {
    file: File,
    stamp: Stamp,
    setup: Setup,
}

#[cfg(target_os = "macos")]
pub fn page_size() -> Result<u64, &'static str> {
    // SAFETY: sysconf takes this integer selector without pointers or ownership.
    let size = unsafe { libc::sysconf(libc::_SC_PAGESIZE) };
    u64::try_from(size)
        .ok()
        .filter(|n| *n > 0)
        .ok_or("PAGE_SIZE")
}
#[cfg(not(target_os = "macos"))]
pub fn page_size() -> Result<u64, &'static str> {
    Err("UNSUPPORTED_PLATFORM")
}

impl FixedDescriptor {
    pub fn open(
        root: &RootDirectory,
        name: &str,
        original: &File,
        policy: Policy,
    ) -> Result<Self, SetupFailure> {
        #[cfg(target_os = "macos")]
        {
            use std::os::fd::AsRawFd;
            Self::open_with(root, name, original, policy, |fresh, arg| {
                // SAFETY: fresh is the independently opened, live read-only file owned by this
                // constructor. Darwin F_NOCACHE accepts the promoted integer argument 0 or 1.
                let returned = unsafe { libc::fcntl(fresh.as_raw_fd(), libc::F_NOCACHE, arg) };
                let errno = if returned < 0 {
                    io::Error::last_os_error().raw_os_error()
                } else {
                    None
                };
                Setter {
                    command: "F_NOCACHE",
                    number: libc::F_NOCACHE,
                    argument: arg,
                    returned,
                    errno,
                }
            })
        }
        #[cfg(not(target_os = "macos"))]
        {
            let _ = (root, name, original, policy);
            Err(SetupFailure {
                reason: "UNSUPPORTED_PLATFORM",
                observation: Setup::default(),
            })
        }
    }

    #[cfg(any(target_os = "macos", test))]
    fn open_with(
        root: &RootDirectory,
        name: &str,
        original: &File,
        policy: Policy,
        set: impl FnOnce(&File, i32) -> Setter,
    ) -> Result<Self, SetupFailure> {
        let mut setup = Setup::default();
        let result = (|| {
            let before = Stamp::read(original).map_err(|_| "ORIGINAL_STAMP")?;
            setup.original_stamp = Some(before.digest());
            // Limit name/error formatting even for callers outside the expert-ranges crate.
            if name.len() > 255
                || name.contains('/')
                || name.contains('\\')
                || name.contains('\0')
                || name.is_empty()
                || name == "."
                || name == ".."
            {
                return Err("SHARD_NAME");
            }
            setup.open_attempted = true;
            let fresh = root.open_file(name).map_err(|_| "FRESH_ADMISSION")?.file;
            setup.fresh_owned = true;
            let stamp = Stamp::read(&fresh).map_err(|_| "FRESH_STAMP")?;
            setup.fresh_stamp = Some(stamp.digest());
            let matched =
                stamp == before && Stamp::read(original).map_err(|_| "ORIGINAL_STAMP")? == before;
            setup.matched = Some(matched);
            if !matched {
                return Err("IDENTITY");
            }
            let call = set(&fresh, policy.argument());
            setup.setter = Some(call);
            if call.returned != 0 {
                return Err("POLICY_SETTER");
            }
            setup.configured = true;
            if Stamp::read(&fresh).map_err(|_| "FRESH_STAMP")? != stamp
                || Stamp::read(original).map_err(|_| "ORIGINAL_STAMP")? != before
            {
                return Err("MUTATION");
            }
            Ok(Self {
                file: fresh,
                stamp,
                setup,
            })
        })();
        result.map_err(|reason| SetupFailure {
            reason,
            observation: setup,
        })
    }
    pub fn setup(&self) -> Setup {
        self.setup
    }
    pub fn check(&self) -> io::Result<()> {
        if Stamp::read(&self.file)? == self.stamp {
            Ok(())
        } else {
            Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "fresh descriptor stamp changed",
            ))
        }
    }
    pub fn read_exact_at(&self, dst: &mut [u8], at: u64) -> io::Result<()> {
        self.file.read_exact_at(dst, at)
    }
}
#[cfg(test)]
mod tests;
