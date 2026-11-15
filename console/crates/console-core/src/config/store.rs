//! The run-config document store: reading a run config, the one atomic writer every
//! subsystem that edits it goes through, the `.prev` backup, the time-keeping save of the
//! Models page, the listing of run configs by recency, and the files kept beside the run
//! config.
//!
//! Every persisted file is resolved relative to the directory of the run config passed with
//! `--config`, as the donor does (lead decision LD26). The default directory when no config
//! is given is open item OPEN-06 and is not chosen here.
//!
//! Files are written as Python's `json.dumps(obj, indent=1)` with `ensure_ascii`, through
//! [`console_pyjson::dumps::to_file`], so an untouched config is rewritten byte for byte.
//! Line endings are written as given (`\n`), as the donor's text-mode write does on POSIX.
//!
//! Behavior reference: project-maya serve/models.py:32-33 and 679-700 (`config_paths`,
//! `read`, `write`), 804-840 (`own_defaults` backup, `_commit` backup and time restore),
//! serve/server.py:2818-2819, 2863-2864, 2918-2919 (other rewrites through the same form),
//! 2932-2934 (`models_root`), 2950-2956 (`_model_path`), 3037 (a switch touches the config),
//! 3155-3158 (the switch note), 7153 (`utf-8-sig` start-up read), 7369 (shared settings
//! path) at 7e68a30f.

use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::{Mutex, MutexGuard};
use std::time::SystemTime;

use console_pyjson::dumps::{to_file, to_python_default};
use console_pyjson::loads::{loads, UnicodeDecodeError};
use serde_json::{Map, Value};

use super::document::{engine_changed, ConfigError, RunConfig};
use super::py;

/// The largest run config read, in bytes. The donor reads any size; run configs are a few
/// kilobytes, and this bound keeps a wrong `--config` path from filling memory. The bound is
/// part of proposal P-23 in the deviation register, awaiting the owner's decision.
pub const MAX_CONFIG_BYTES: u64 = 16 * 1024 * 1024;

/// The prefix of run-config file names (decision B2; donor `maya-`).
pub const CONFIG_PREFIX: &str = "pulsar-";

/// The suffix of the Chat settings shared with other apps, kept beside a run config.
pub const SHARED_SETTINGS_SUFFIX: &str = ".shared-settings.json";

/// The note asking the supervisor to start another run config next (decision B2; donor
/// `.maya-switch.json`).
pub const SWITCH_FILE: &str = ".pulsar-switch.json";

/// The note asking the next server to delete a run config (decision B2; donor
/// `.maya-delete.json`).
pub const DELETE_FILE: &str = ".pulsar-delete.json";

/// The directory a run config's sibling files live in: the config's parent, `.` for a bare
/// file name (Python's `Path(config).parent`).
pub fn config_dir(config: &Path) -> PathBuf {
    match config.parent() {
        Some(p) if !p.as_os_str().is_empty() => p.to_path_buf(),
        _ => PathBuf::from("."),
    }
}

/// `path` with `suffix` appended to its file name (Python's `p.with_name(p.name + suffix)`).
fn with_name_suffix(path: &Path, suffix: &str) -> PathBuf {
    let mut name = path
        .file_name()
        .map(|n| n.to_os_string())
        .unwrap_or_default();
    name.push(suffix);
    path.with_file_name(name)
}

fn io_error(path: &Path, source: std::io::Error) -> ConfigError {
    ConfigError::Io {
        path: path.to_path_buf(),
        source,
    }
}

/// Reads at most [`MAX_CONFIG_BYTES`] of a file.
fn read_bounded(path: &Path) -> Result<Vec<u8>, ConfigError> {
    let file = fs::File::open(path).map_err(|e| io_error(path, e))?;
    let mut bytes = Vec::new();
    file.take(MAX_CONFIG_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| io_error(path, e))?;
    if bytes.len() as u64 > MAX_CONFIG_BYTES {
        return Err(ConfigError::TooLarge {
            path: path.to_path_buf(),
        });
    }
    Ok(bytes)
}

/// Python's strict `utf-8-sig` decoding followed by text-mode newline translation
/// (`\r\n` and `\r` become `\n`), as `Path.read_text(encoding="utf-8-sig")` does.
fn decode_utf8_sig(bytes: &[u8]) -> Result<String, UnicodeDecodeError> {
    let body = bytes.strip_prefix(b"\xef\xbb\xbf").unwrap_or(bytes);
    let text = match std::str::from_utf8(body) {
        Ok(t) => t,
        Err(e) => {
            let start = e.valid_up_to();
            let first = body.get(start).copied().unwrap_or(0);
            return Err(match e.error_len() {
                None => UnicodeDecodeError {
                    encoding: "utf-8",
                    first_byte: first,
                    start,
                    end: body.len(),
                    reason: "unexpected end of data",
                },
                Some(1) if matches!(first, 0x80..=0xc1 | 0xf5..=0xff) => UnicodeDecodeError {
                    encoding: "utf-8",
                    first_byte: first,
                    start,
                    end: start + 1,
                    reason: "invalid start byte",
                },
                Some(n) => UnicodeDecodeError {
                    encoding: "utf-8",
                    first_byte: first,
                    start,
                    end: start + n,
                    reason: "invalid continuation byte",
                },
            });
        }
    };
    if text.contains('\r') {
        Ok(text.replace("\r\n", "\n").replace('\r', "\n"))
    } else {
        Ok(text.to_string())
    }
}

/// Reads a run config as the server does at start-up: UTF-8 with a tolerated byte-order
/// mark, parsed as Python's `json.loads`, keys in order.
///
/// # Errors
///
/// [`ConfigError::Io`], [`ConfigError::TooLarge`], [`ConfigError::Unicode`],
/// [`ConfigError::Json`] (Python's message), or [`ConfigError::NotAnObject`]; the server
/// does not start.
///
/// Behavior reference: project-maya serve/server.py:7153 at 7e68a30f.
pub fn load_document(path: &Path) -> Result<RunConfig, ConfigError> {
    let bytes = read_bounded(path)?;
    let text = decode_utf8_sig(&bytes).map_err(|error| ConfigError::Unicode {
        path: path.to_path_buf(),
        error,
    })?;
    match loads(&text) {
        Ok(Value::Object(map)) => Ok(RunConfig::from(map)),
        Ok(_) => Err(ConfigError::NotAnObject {
            path: path.to_path_buf(),
        }),
        Err(error) => Err(ConfigError::Json {
            path: path.to_path_buf(),
            error,
        }),
    }
}

/// Reads a run config as the Models page does: anything that cannot be read, decoded or
/// parsed, and any JSON that is not an object, reads as an empty config, never an error.
/// A file above [`MAX_CONFIG_BYTES`] and a document nested deeper than the reader's bound
/// (proposal P-20) also read as empty, where the donor reads the first and stops on the
/// second; both differences await the owner's decision (proposals P-23 and P-20).
///
/// Behavior reference: project-maya serve/models.py:688-693 at 7e68a30f.
pub fn read_document(path: &Path) -> RunConfig {
    load_document(path).unwrap_or_default()
}

/// The text of a run config file: Python's `json.dumps(doc, indent=1)`.
///
/// # Errors
///
/// [`ConfigError::Encode`] for a value Python cannot write either.
pub fn document_text(path: &Path, doc: &RunConfig) -> Result<String, ConfigError> {
    to_file(&doc.to_value()).map_err(|error| ConfigError::Encode {
        path: path.to_path_buf(),
        error,
    })
}

/// Serializes every write of this module within the process, so two writers never share
/// the fixed `<name>.tmp` file.
static WRITE_LOCK: Mutex<()> = Mutex::new(());

/// Takes [`WRITE_LOCK`]; a writer that panicked leaves no state the lock protects.
fn write_lock() -> MutexGuard<'static, ()> {
    WRITE_LOCK
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

/// The permissions of an existing file, `None` when it cannot be read.
fn permissions_of(path: &Path) -> Option<fs::Permissions> {
    fs::metadata(path).ok().map(|m| m.permissions())
}

/// Writes `bytes` to `path` (created or truncated), gives it `perms` when given, and flushes
/// it to the disk.
fn write_file(
    path: &Path,
    bytes: &[u8],
    perms: Option<fs::Permissions>,
) -> Result<(), ConfigError> {
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .open(path)
        .map_err(|e| io_error(path, e))?;
    if let Some(perms) = perms {
        file.set_permissions(perms).map_err(|e| io_error(path, e))?;
    }
    file.write_all(bytes).map_err(|e| io_error(path, e))?;
    file.sync_all().map_err(|e| io_error(path, e))
}

/// [`write_document`] with [`WRITE_LOCK`] already held.
fn write_document_held(path: &Path, doc: &RunConfig) -> Result<(), ConfigError> {
    let text = document_text(path, doc)?;
    let tmp = with_name_suffix(path, ".tmp");
    write_file(&tmp, text.as_bytes(), permissions_of(path))?;
    fs::rename(&tmp, path).map_err(|e| io_error(path, e))
}

/// Writes a run config atomically: the text goes to `<name>.tmp` beside it, which is flushed
/// to the disk and then renamed over `<name>`. Every subsystem that edits a run config uses
/// this writer. Writes within the process are serialized, and the new file keeps the
/// permissions of the one it replaces (the run config holds secrets; the donor's file gets
/// the default mode instead, which byte parity does not cover).
///
/// # Errors
///
/// [`ConfigError::Encode`] before anything is written, or [`ConfigError::Io`].
///
/// Behavior reference: project-maya serve/models.py:696-700 at 7e68a30f.
pub fn write_document(path: &Path, doc: &RunConfig) -> Result<(), ConfigError> {
    let _guard = write_lock();
    write_document_held(path, doc)
}

/// The backup beside a run config, `<name>.prev`.
pub fn prev_path(path: &Path) -> PathBuf {
    with_name_suffix(path, ".prev")
}

/// [`write_prev`] with [`WRITE_LOCK`] already held.
fn write_prev_held(path: &Path, previous: &RunConfig) -> Result<PathBuf, ConfigError> {
    let prev = prev_path(path);
    let text = document_text(&prev, previous)?;
    write_file(&prev, text.as_bytes(), permissions_of(path))?;
    Ok(prev)
}

/// Writes the previous whole document to `<name>.prev`, directly (not atomically), as the
/// donor does. The backup gets the run config's permissions when the config exists.
///
/// # Errors
///
/// [`ConfigError::Encode`] or [`ConfigError::Io`].
///
/// Behavior reference: project-maya serve/models.py:817 and 836-837 at 7e68a30f.
pub fn write_prev(path: &Path, previous: &RunConfig) -> Result<PathBuf, ConfigError> {
    let _guard = write_lock();
    write_prev_held(path, previous)
}

/// A file's access and modification times.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FileTimes {
    /// Last access.
    pub accessed: SystemTime,
    /// Last modification.
    pub modified: SystemTime,
}

/// Reads a file's access and modification times.
///
/// # Errors
///
/// [`ConfigError::Io`].
pub fn file_times(path: &Path) -> Result<FileTimes, ConfigError> {
    let meta = fs::metadata(path).map_err(|e| io_error(path, e))?;
    Ok(FileTimes {
        accessed: meta.accessed().map_err(|e| io_error(path, e))?,
        modified: meta.modified().map_err(|e| io_error(path, e))?,
    })
}

/// Sets a file's access and modification times (Python's `os.utime(path, (atime, mtime))`).
/// On Unix the file is opened for reading, so the owner can set the times of a read-only
/// file as `os.utime` can; elsewhere it is opened for writing, which the platform requires.
///
/// # Errors
///
/// [`ConfigError::Io`].
pub fn set_file_times(path: &Path, times: FileTimes) -> Result<(), ConfigError> {
    let mut options = fs::OpenOptions::new();
    if cfg!(unix) {
        options.read(true);
    } else {
        options.write(true);
    }
    let file = options.open(path).map_err(|e| io_error(path, e))?;
    file.set_times(
        fs::FileTimes::new()
            .set_accessed(times.accessed)
            .set_modified(times.modified),
    )
    .map_err(|e| io_error(path, e))
}

/// Writes a run config atomically and gives it back the access and modification times it
/// had before, so a save from the Models page does not change which config starts next.
///
/// # Errors
///
/// [`ConfigError::Encode`] or [`ConfigError::Io`].
///
/// Behavior reference: project-maya serve/models.py:818-820 and 838-839 at 7e68a30f.
pub fn write_keeping_times(path: &Path, doc: &RunConfig) -> Result<(), ConfigError> {
    let _guard = write_lock();
    write_keeping_times_held(path, doc)
}

/// [`write_keeping_times`] with [`WRITE_LOCK`] already held.
fn write_keeping_times_held(path: &Path, doc: &RunConfig) -> Result<(), ConfigError> {
    let before = file_times(path)?;
    write_document_held(path, doc)?;
    set_file_times(path, before)
}

/// Sets a run config's access and modification times to now, so the next start picks it
/// (a switch on the Models page; Python's `os.utime(path)`).
///
/// # Errors
///
/// [`ConfigError::Io`].
///
/// Behavior reference: project-maya serve/server.py:3037 at 7e68a30f.
pub fn touch(path: &Path) -> Result<(), ConfigError> {
    let now = SystemTime::now();
    set_file_times(
        path,
        FileTimes {
            accessed: now,
            modified: now,
        },
    )
}

/// What a save from the Models page did.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CommitOutcome {
    /// The engine's command or environment changed, so a restart is due.
    pub changed: bool,
    /// The name of the backup written, `<name>.prev`; `None` when nothing was saved because
    /// the new document equals the old.
    pub prev: Option<String>,
}

/// The file part of a save from the Models page: nothing when `new` equals `old` (Python
/// equality); otherwise the first save records `installer.as_set_up` (the value
/// `as_set_up` computes from `old`, the Models page's own reading of the settings), `old` is
/// written to `<name>.prev`, `new` is written atomically, and the config keeps its times.
///
/// # Errors
///
/// [`ConfigError::Invalid`] when `new` has an `installer` that is not an object (the donor
/// raises a `TypeError` there; the console's message differs, which is part of proposal
/// P-23, awaiting the owner's decision), [`ConfigError::Encode`] or
/// [`ConfigError::Io`].
///
/// Behavior reference: project-maya serve/models.py:825-840 at 7e68a30f.
pub fn commit(
    path: &Path,
    old: &RunConfig,
    mut new: RunConfig,
    as_set_up: impl FnOnce(&RunConfig) -> Value,
) -> Result<CommitOutcome, ConfigError> {
    let changed = engine_changed(old, &new);
    if new == *old {
        return Ok(CommitOutcome {
            changed: false,
            prev: None,
        });
    }
    let installer = new
        .as_map_mut()
        .entry("installer")
        .or_insert_with(|| Value::Object(Map::new()));
    match installer {
        Value::Object(inst) => {
            if !inst.contains_key("as_set_up") {
                inst.insert(String::from("as_set_up"), as_set_up(old));
            }
        }
        _ => {
            return Err(ConfigError::Invalid(String::from(
                "\"installer\" must be an object",
            )))
        }
    }
    let _guard = write_lock();
    let prev = write_prev_held(path, old)?;
    write_keeping_times_held(path, &new)?;
    Ok(CommitOutcome {
        changed,
        prev: prev.file_name().map(|n| n.to_string_lossy().into_owned()),
    })
}

/// The run configs in a directory, the most recently used first: every entry matching the
/// glob `pulsar-*.json` (case-sensitive, `*` possibly empty) whose name does not end with
/// [`SHARED_SETTINGS_SUFFIX`], ordered by modification time,
/// newest first (equal times by name). Any error reading the directory or a file's time
/// gives an empty list, as in the donor.
///
/// Behavior reference: project-maya serve/models.py:679-685 at 7e68a30f.
pub fn config_paths(dir: &Path) -> Vec<PathBuf> {
    fn listed(dir: &Path) -> std::io::Result<Vec<(SystemTime, PathBuf)>> {
        let mut found = Vec::new();
        for entry in fs::read_dir(dir)? {
            let entry = entry?;
            let name = entry.file_name();
            let Some(name) = name.to_str() else {
                continue;
            };
            // The glob `pulsar-*.json`: `*` may be empty, so `pulsar-.json` is listed.
            if name.len() >= CONFIG_PREFIX.len() + ".json".len()
                && name.starts_with(CONFIG_PREFIX)
                && name.ends_with(".json")
                && !name.ends_with(SHARED_SETTINGS_SUFFIX)
            {
                let path = entry.path();
                let modified = fs::metadata(&path)?.modified()?;
                found.push((modified, path));
            }
        }
        Ok(found)
    }
    match listed(dir) {
        Ok(mut found) => {
            found.sort_by(|a, b| a.1.cmp(&b.1));
            found.sort_by_key(|e| std::cmp::Reverse(e.0));
            found.into_iter().map(|(_, p)| p).collect()
        }
        Err(_) => Vec::new(),
    }
}

/// Whether a name is a run-config file name: `pulsar-<one or more characters other than / and
/// \>.json`, not ending with [`SHARED_SETTINGS_SUFFIX`]. No regular expression is used.
///
/// Behavior reference: project-maya serve/server.py:2953 at 7e68a30f.
pub fn is_config_file_name(name: &str) -> bool {
    let Some(rest) = name.strip_prefix(CONFIG_PREFIX) else {
        return false;
    };
    let Some(middle) = rest.strip_suffix(".json") else {
        return false;
    };
    !middle.is_empty() && !middle.contains(['/', '\\']) && !name.ends_with(SHARED_SETTINGS_SUFFIX)
}

/// The message of a request naming a run config that is not here.
pub fn no_config_message(name: &str) -> String {
    format!("no model config named {} here", py::repr_str(name))
}

/// A run config named by a request (`"file"`): its path in `dir` when the name is a run-config
/// file name and the file exists there.
///
/// # Errors
///
/// [`no_config_message`] otherwise; the route answers it as a 400 `invalid_request_error`.
///
/// Behavior reference: project-maya serve/server.py:2950-2956 at 7e68a30f.
pub fn checked_config_path(dir: &Path, name: &str) -> Result<PathBuf, String> {
    let path = dir.join(name);
    if is_config_file_name(name) && path.is_file() {
        Ok(path)
    } else {
        Err(no_config_message(name))
    }
}

/// The run config passed with `--config`, and the files resolved beside it (lead decision
/// LD26).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RunConfigStore {
    path: PathBuf,
}

impl RunConfigStore {
    /// The store of the run config at `path`, as given on the command line.
    pub fn new(path: impl Into<PathBuf>) -> Self {
        RunConfigStore { path: path.into() }
    }

    /// The run config's path.
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// The directory every persisted file is resolved in: the run config's
    /// ([`config_dir`]).
    ///
    /// Behavior reference: project-maya serve/server.py:2932-2934 at 7e68a30f.
    pub fn dir(&self) -> PathBuf {
        config_dir(&self.path)
    }

    /// A file in the run config's directory.
    pub fn resolve(&self, name: impl AsRef<Path>) -> PathBuf {
        self.dir().join(name)
    }

    /// The backup, `<config>.prev`.
    pub fn prev_path(&self) -> PathBuf {
        prev_path(&self.path)
    }

    /// The temporary file of an atomic write, `<config>.tmp`.
    pub fn tmp_path(&self) -> PathBuf {
        with_name_suffix(&self.path, ".tmp")
    }

    /// The Chat settings shared with other apps: the config's path without its last
    /// extension, plus [`SHARED_SETTINGS_SUFFIX`].
    ///
    /// Behavior reference: project-maya serve/server.py:7369 at 7e68a30f.
    pub fn shared_settings_path(&self) -> PathBuf {
        let mut name = self
            .path
            .file_stem()
            .map(|n| n.to_os_string())
            .unwrap_or_default();
        name.push(SHARED_SETTINGS_SUFFIX);
        self.path.with_file_name(name)
    }

    /// The switch note, in the run config's directory.
    pub fn switch_note_path(&self) -> PathBuf {
        self.resolve(SWITCH_FILE)
    }

    /// The delete note, in the run config's directory.
    pub fn delete_note_path(&self) -> PathBuf {
        self.resolve(DELETE_FILE)
    }

    /// Reads the run config strictly ([`load_document`]), as at start-up.
    ///
    /// # Errors
    ///
    /// As [`load_document`].
    pub fn load(&self) -> Result<RunConfig, ConfigError> {
        load_document(&self.path)
    }

    /// Reads the run config leniently ([`read_document`]).
    pub fn read(&self) -> RunConfig {
        read_document(&self.path)
    }

    /// Writes the run config atomically ([`write_document`]).
    ///
    /// # Errors
    ///
    /// As [`write_document`].
    pub fn write(&self, doc: &RunConfig) -> Result<(), ConfigError> {
        write_document(&self.path, doc)
    }

    /// Reads the run config strictly, lets `edit` change it, and writes it back atomically:
    /// the read-modify-write of the server's own edits (context, thinking budget, port).
    /// Unknown keys and key order survive; a key `edit` adds goes last. The module's write
    /// lock is held from the read to the rename, so `edit` must not write a run config itself.
    ///
    /// # Errors
    ///
    /// As [`load_document`] and [`write_document`]; nothing is written when the read fails.
    ///
    /// Behavior reference: project-maya serve/server.py:2860-2864 and 2915-2919 at 7e68a30f.
    pub fn update(&self, edit: impl FnOnce(&mut RunConfig)) -> Result<RunConfig, ConfigError> {
        let _guard = write_lock();
        let mut doc = self.load()?;
        edit(&mut doc);
        write_document_held(&self.path, &doc)?;
        Ok(doc)
    }

    /// Lists the run configs beside this one ([`config_paths`]).
    pub fn config_paths(&self) -> Vec<PathBuf> {
        config_paths(&self.dir())
    }

    /// Resolves a run config named by a request ([`checked_config_path`]).
    ///
    /// # Errors
    ///
    /// As [`checked_config_path`].
    pub fn checked_config_path(&self, name: &str) -> Result<PathBuf, String> {
        checked_config_path(&self.dir(), name)
    }
}

/// Writes a note file (the switch and delete notes) as Python's bare `json.dumps(note)`
/// (separators `", "` and `": "`, `ensure_ascii`), directly.
///
/// # Errors
///
/// [`ConfigError::Encode`] or [`ConfigError::Io`].
///
/// Behavior reference: project-maya serve/server.py:3157 at 7e68a30f.
pub fn write_note(path: &Path, note: &Value) -> Result<(), ConfigError> {
    let text = to_python_default(note).map_err(|error| ConfigError::Encode {
        path: path.to_path_buf(),
        error,
    })?;
    let _guard = write_lock();
    write_file(path, text.as_bytes(), None)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn config_file_names() {
        for good in [
            "pulsar-a.json",
            "pulsar-.json.json",
            "pulsar- x .json",
            "pulsar-\n.json",
        ] {
            assert!(is_config_file_name(good), "{good:?}");
        }
        for bad in [
            "pulsar-.json",
            "maya-a.json",
            "pulsar-a/b.json",
            "pulsar-a\\b.json",
            "pulsar-a.json.tmp",
            "pulsar-a.shared-settings.json",
            "Pulsar-a.json",
            "",
        ] {
            assert!(!is_config_file_name(bad), "{bad:?}");
        }
    }

    #[test]
    fn missing_config_message_uses_python_repr() {
        assert_eq!(no_config_message("x"), "no model config named 'x' here");
        assert_eq!(
            no_config_message("it's"),
            "no model config named \"it's\" here"
        );
        assert_eq!(no_config_message(""), "no model config named '' here");
    }

    #[test]
    fn sibling_paths() {
        let s = RunConfigStore::new(Path::new("cfgdir").join("pulsar-m.json"));
        assert_eq!(s.dir(), PathBuf::from("cfgdir"));
        assert_eq!(
            s.prev_path(),
            Path::new("cfgdir").join("pulsar-m.json.prev")
        );
        assert_eq!(s.tmp_path(), Path::new("cfgdir").join("pulsar-m.json.tmp"));
        assert_eq!(
            s.shared_settings_path(),
            Path::new("cfgdir").join("pulsar-m.shared-settings.json")
        );
        assert_eq!(s.switch_note_path(), Path::new("cfgdir").join(SWITCH_FILE));
        assert_eq!(s.delete_note_path(), Path::new("cfgdir").join(DELETE_FILE));
        assert_eq!(
            s.resolve("token-savings.json"),
            Path::new("cfgdir").join("token-savings.json")
        );
        let bare = RunConfigStore::new("pulsar-m.json");
        assert_eq!(bare.dir(), PathBuf::from("."));
        assert_eq!(bare.resolve("x"), Path::new(".").join("x"));
    }

    #[test]
    fn utf8_sig_decoding() {
        assert_eq!(
            decode_utf8_sig(b"\xef\xbb\xbf{}").ok().as_deref(),
            Some("{}")
        );
        assert_eq!(
            decode_utf8_sig(b"a\r\nb\rc").ok().as_deref(),
            Some("a\nb\nc")
        );
        let e = decode_utf8_sig(b"{\xff}").err().map(|e| e.to_string());
        assert_eq!(
            e.as_deref(),
            Some("'utf-8' codec can't decode byte 0xff in position 1: invalid start byte")
        );
        let e = decode_utf8_sig(b"\xef\xbb\xbf\xe2\x82")
            .err()
            .map(|e| e.to_string());
        assert_eq!(
            e.as_deref(),
            Some("'utf-8' codec can't decode bytes in position 0-1: unexpected end of data")
        );
        let e = decode_utf8_sig(b"\xed\xa0\x80")
            .err()
            .map(|e| e.to_string());
        assert_eq!(
            e.as_deref(),
            Some("'utf-8' codec can't decode byte 0xed in position 0: invalid continuation byte")
        );
    }
}
