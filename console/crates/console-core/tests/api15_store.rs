//! API-15: the run-config document store. An untouched config is rewritten byte for byte as
//! Python's `json.dumps(obj, indent=1)` wrote it, unknown nested keys survive a
//! read-modify-write with their order, a byte-order mark is tolerated, an unreadable file
//! reads as an empty config on the lenient path and as an error at start-up, saves keep the
//! file's times, a switch advances them, and run configs are listed newest first.
//!
//! The golden texts were recorded with CPython 3's standard `json` module alone
//! (`python3 -I`), never by running the donor. Every test writes only under a temporary
//! directory it creates and removes.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::{Duration, SystemTime};

use console_core::config::{
    checked_config_path, commit, config_paths, file_times, load_document, read_document,
    set_file_times, touch, write_document, write_keeping_times, write_note, ConfigError, FileTimes,
    RunConfig, RunConfigStore, MAX_CONFIG_BYTES, SWITCH_FILE,
};
use console_pyjson::loads::loads;
use serde_json::Value;

/// A directory under the system temporary directory, removed on drop.
struct TempDir(PathBuf);

impl TempDir {
    fn new() -> TempDir {
        static NEXT: AtomicUsize = AtomicUsize::new(0);
        let tag = console_pyjson::ids::hex12().unwrap_or_else(|_| String::from("x"));
        let dir = std::env::temp_dir().join(format!(
            "api15-store-{}-{}-{tag}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&dir).expect("temporary directory");
        TempDir(dir)
    }

    fn path(&self, name: &str) -> PathBuf {
        self.0.join(name)
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn value(text: &str) -> Value {
    loads(text).expect("test JSON")
}

fn object(text: &str) -> RunConfig {
    match value(text) {
        Value::Object(m) => RunConfig::from(m),
        other => panic!("not an object: {other}"),
    }
}

/// Python `json.dumps(doc, indent=1)` texts, recorded from CPython 3: non-ASCII and astral
/// characters escaped, floats in `repr` form, nested and empty containers, unknown keys,
/// controls and quotes in strings.
const GOLDEN: &[&str] = &[
    "{\n \"exe\": \"/b/engine\",\n \"args\": [\n  \"--pack\",\n  \"/p\",\n  \"--max-context\",\n  \"131072\"\n ],\n \"model_name\": \"caf\\u00e9-\\u4e2d\\u6587-\\ud83d\\ude00\",\n \"gpu\": [\n  0,\n  1\n ],\n \"port\": 8080,\n \"sampling\": {\n  \"temperature\": 1.0,\n  \"top_p\": 0.95,\n  \"min_p\": 1e-05,\n  \"big\": 1e+16,\n  \"neg\": -0.0\n },\n \"env\": {\n  \"MAYA_GLM_SLOT_KEEP\": \"1\",\n  \"HF_TOKEN\": \"hf_x\"\n },\n \"installer\": {\n  \"nested\": {\n   \"deeper\": {\n    \"keep\": [\n     true,\n     false,\n     null\n    ]\n   }\n  },\n  \"empty_list\": [],\n  \"empty_obj\": {}\n },\n \"zz_unknown\": {\n  \"b\": 2,\n  \"a\": 1\n },\n \"tab\\tkey\": \"line\\nbreak \\\"q\\\" \\\\ \\u007f \\u0001\"\n}",
    "{}",
    "{\n \"a\": []\n}",
    "{\n \"a\": {},\n \"b\": [\n  [],\n  {}\n ],\n \"c\": [\n  1,\n  [\n   2,\n   [\n    3,\n    {}\n   ]\n  ]\n ]\n}",
    "{\n \"f\": [\n  0.1,\n  2.5,\n  100.0,\n  1.5e-07,\n  123456789012345678,\n  3.141592653589793\n ]\n}",
];

#[test]
fn an_untouched_config_is_rewritten_byte_for_byte() {
    let dir = TempDir::new();
    for (i, golden) in GOLDEN.iter().enumerate() {
        let path = dir.path(&format!("pulsar-g{i}.json"));
        fs::write(&path, golden).expect("write golden");
        let doc = load_document(&path).expect("load golden");
        write_document(&path, &doc).expect("rewrite");
        let after = fs::read_to_string(&path).expect("read back");
        assert_eq!(after, *golden, "golden {i}");
        assert!(!dir.path(&format!("pulsar-g{i}.json.tmp")).exists());
    }
}

#[test]
fn unknown_nested_keys_survive_a_read_modify_write_in_order() {
    let dir = TempDir::new();
    let store = RunConfigStore::new(dir.path("pulsar-m.json"));
    fs::write(store.path(), GOLDEN[0]).expect("write");
    let doc = store
        .update(|d| {
            d.set("port", Value::from(9090));
            d.set("thinking_budget", Value::from(8192));
        })
        .expect("update");
    let keys: Vec<&str> = doc.as_map().keys().map(String::as_str).collect();
    assert_eq!(
        keys,
        [
            "exe",
            "args",
            "model_name",
            "gpu",
            "port",
            "sampling",
            "env",
            "installer",
            "zz_unknown",
            "tab\tkey",
            "thinking_budget"
        ]
    );
    let text = fs::read_to_string(store.path()).expect("read");
    let replaced = GOLDEN[0].replace("\"port\": 8080", "\"port\": 9090");
    let body = replaced.strip_suffix("\n}").expect("document end");
    assert_eq!(text, format!("{body},\n \"thinking_budget\": 8192\n}}"));
    let reread = read_document(store.path());
    let zz = reread.get("zz_unknown").expect("kept");
    assert_eq!(
        zz.as_object()
            .map(|m| m.keys().cloned().collect::<Vec<_>>()),
        Some(vec![String::from("b"), String::from("a")])
    );
}

#[test]
fn a_byte_order_mark_is_tolerated() {
    let dir = TempDir::new();
    let path = dir.path("pulsar-bom.json");
    let mut bytes = b"\xef\xbb\xbf".to_vec();
    bytes.extend_from_slice(b"{\r\n \"a\": 1\r\n}");
    fs::write(&path, &bytes).expect("write");
    let doc = load_document(&path).expect("BOM tolerated");
    assert_eq!(doc.get("a"), Some(&Value::from(1)));
    write_document(&path, &doc).expect("rewrite");
    assert_eq!(fs::read(&path).expect("read"), b"{\n \"a\": 1\n}");
}

#[test]
fn unreadable_configs_read_as_empty_but_stop_a_start() {
    let dir = TempDir::new();
    let cases: &[(&str, &[u8])] = &[
        ("pulsar-bad.json", b"{\"a\": "),
        ("pulsar-list.json", b"[1, 2]"),
        ("pulsar-bytes.json", b"{\"a\": \"\xff\"}"),
        ("pulsar-twobom.json", b"\xef\xbb\xbf\xef\xbb\xbf{}"),
    ];
    for (name, bytes) in cases {
        let path = dir.path(name);
        fs::write(&path, bytes).expect("write");
        assert!(read_document(&path).is_empty(), "{name}");
        assert!(load_document(&path).is_err(), "{name}");
    }
    let missing = dir.path("pulsar-none.json");
    assert!(read_document(&missing).is_empty());
    assert!(matches!(
        load_document(&missing),
        Err(ConfigError::Io { .. })
    ));
    match load_document(&dir.path("pulsar-bad.json")) {
        Err(ConfigError::Json { error, .. }) => {
            assert_eq!(
                error.to_string(),
                "Expecting value: line 1 column 7 (char 6)"
            )
        }
        other => panic!("{other:?}"),
    }
    match load_document(&dir.path("pulsar-twobom.json")) {
        Err(ConfigError::Json { error, .. }) => assert_eq!(
            error.to_string(),
            "Unexpected UTF-8 BOM (decode using utf-8-sig): line 1 column 1 (char 0)"
        ),
        other => panic!("{other:?}"),
    }
    assert!(matches!(
        load_document(&dir.path("pulsar-list.json")),
        Err(ConfigError::NotAnObject { .. })
    ));
    match load_document(&dir.path("pulsar-bytes.json")) {
        Err(ConfigError::Unicode { error, .. }) => assert_eq!(
            error.to_string(),
            "'utf-8' codec can't decode byte 0xff in position 7: invalid start byte"
        ),
        other => panic!("{other:?}"),
    }
}

#[test]
fn an_oversized_file_is_refused() {
    let dir = TempDir::new();
    let path = dir.path("pulsar-big.json");
    let size = usize::try_from(MAX_CONFIG_BYTES).expect("fits") + 1;
    let mut text = String::with_capacity(size);
    text.push_str("{\"a\": \"");
    text.push_str(&"x".repeat(size - 9));
    text.push_str("\"}");
    fs::write(&path, text).expect("write");
    assert!(matches!(
        load_document(&path),
        Err(ConfigError::TooLarge { .. })
    ));
    assert!(read_document(&path).is_empty());
}

#[test]
fn a_failed_read_writes_nothing() {
    let dir = TempDir::new();
    let store = RunConfigStore::new(dir.path("pulsar-x.json"));
    fs::write(store.path(), "not json").expect("write");
    assert!(store.update(|d| d.set("port", Value::from(1))).is_err());
    assert_eq!(fs::read_to_string(store.path()).expect("read"), "not json");
}

fn set_mtime(path: &Path, when: SystemTime) {
    set_file_times(
        path,
        FileTimes {
            accessed: when,
            modified: when,
        },
    )
    .expect("set times");
}

#[test]
fn a_save_keeps_the_file_s_times_and_a_switch_advances_them() {
    let dir = TempDir::new();
    let path = dir.path("pulsar-t.json");
    write_document(&path, &object("{\"port\": 1}")).expect("write");
    let old = SystemTime::now() - Duration::from_secs(1000);
    set_mtime(&path, old);
    write_keeping_times(&path, &object("{\"port\": 2}")).expect("save");
    assert_eq!(file_times(&path).expect("times").modified, old);
    assert_eq!(read_document(&path).get("port"), Some(&Value::from(2)));
    touch(&path).expect("touch");
    let now = file_times(&path).expect("times").modified;
    assert!(now > old + Duration::from_secs(900));
}

#[test]
fn commit_backs_up_records_the_setup_and_keeps_times() {
    let dir = TempDir::new();
    let path = dir.path("pulsar-c.json");
    let old_doc = object("{\"args\": [\"--max-context\", \"131072\"], \"port\": 8080, \"installer\": {\"quant\": \"q\"}}");
    write_document(&path, &old_doc).expect("write");
    let when = SystemTime::now() - Duration::from_secs(1000);
    set_mtime(&path, when);

    // Equal by Python's rules (1 == 1.0): nothing written, no backup.
    let same = object("{\"args\": [\"--max-context\", \"131072\"], \"port\": 8080.0, \"installer\": {\"quant\": \"q\"}}");
    let out = commit(&path, &old_doc, same, |_| Value::Null).expect("commit");
    assert_eq!((out.changed, out.prev), (false, None));
    assert!(!dir.path("pulsar-c.json.prev").exists());

    let mut new_doc = old_doc.clone();
    new_doc.set("args", value("[\"--max-context\", \"65536\"]"));
    let out = commit(&path, &old_doc, new_doc, |cfg| {
        cfg.get("port").cloned().unwrap_or(Value::Null)
    })
    .expect("commit");
    assert!(out.changed);
    assert_eq!(out.prev.as_deref(), Some("pulsar-c.json.prev"));
    assert_eq!(read_document(&dir.path("pulsar-c.json.prev")), old_doc);
    let saved = read_document(&path);
    assert_eq!(
        saved.get("args"),
        Some(&value("[\"--max-context\", \"65536\"]"))
    );
    assert_eq!(
        saved.get("installer"),
        Some(&value("{\"quant\": \"q\", \"as_set_up\": 8080}"))
    );
    assert_eq!(file_times(&path).expect("times").modified, when);

    // The second save keeps the first as_set_up; a change outside the engine keys is no restart.
    let mut port_only = saved.clone();
    port_only.set("port", Value::from(9000));
    let out = commit(&path, &saved, port_only, |_| Value::from("never")).expect("commit");
    assert!(!out.changed);
    assert_eq!(
        read_document(&path).get("installer"),
        Some(&value("{\"quant\": \"q\", \"as_set_up\": 8080}"))
    );

    let mut broken = saved.clone();
    broken.set("installer", Value::from("text"));
    assert!(matches!(
        commit(&path, &saved, broken, |_| Value::Null),
        Err(ConfigError::Invalid(_))
    ));
}

#[test]
fn run_configs_are_listed_newest_first() {
    let dir = TempDir::new();
    let base = SystemTime::now() - Duration::from_secs(10_000);
    let files = [
        ("pulsar-old.json", 10),
        ("pulsar-new.json", 300),
        ("pulsar-mid.json", 200),
        ("pulsar-.json", 100),
        ("pulsar-mid.shared-settings.json", 400),
        ("maya-other.json", 500),
        ("pulsar-x.json.prev", 500),
        ("Pulsar-y.json", 500),
    ];
    for (name, secs) in files {
        let p = dir.path(name);
        fs::write(&p, "{}").expect("write");
        set_mtime(&p, base + Duration::from_secs(secs));
    }
    let listed: Vec<String> = config_paths(&dir.0)
        .iter()
        .filter_map(|p| p.file_name().map(|n| n.to_string_lossy().into_owned()))
        .collect();
    assert_eq!(
        listed,
        [
            "pulsar-new.json",
            "pulsar-mid.json",
            "pulsar-.json",
            "pulsar-old.json"
        ]
    );
    assert!(config_paths(&dir.path("missing")).is_empty());
    let store = RunConfigStore::new(dir.path("pulsar-old.json"));
    assert_eq!(store.config_paths().len(), 4);
}

#[test]
fn a_named_config_must_be_here() {
    let dir = TempDir::new();
    fs::write(dir.path("pulsar-a.json"), "{}").expect("write");
    fs::create_dir(dir.path("pulsar-d.json")).expect("dir");
    let store = RunConfigStore::new(dir.path("pulsar-a.json"));
    assert_eq!(
        store.checked_config_path("pulsar-a.json"),
        Ok(dir.path("pulsar-a.json"))
    );
    for name in [
        "pulsar-b.json",
        "pulsar-d.json",
        "../pulsar-a.json",
        "maya-a.json",
        "pulsar-a.shared-settings.json",
    ] {
        assert_eq!(
            checked_config_path(&dir.0, name),
            Err(format!("no model config named '{name}' here"))
        );
    }
}

#[test]
fn notes_are_written_compact() {
    let dir = TempDir::new();
    let store = RunConfigStore::new(dir.path("pulsar-a.json"));
    let note = value("{\"config\": \"/c/pulsar-\u{e9}.json\", \"port\": 8095, \"why\": \"switch\", \"time\": 1.5}");
    write_note(&store.switch_note_path(), &note).expect("note");
    assert_eq!(
        fs::read_to_string(dir.path(SWITCH_FILE)).expect("read"),
        "{\"config\": \"/c/pulsar-\\u00e9.json\", \"port\": 8095, \"why\": \"switch\", \"time\": 1.5}"
    );
}

#[cfg(unix)]
#[test]
fn the_owner_sets_the_times_of_a_read_only_config() {
    let dir = TempDir::new();
    let path = dir.path("pulsar-ro.json");
    write_document(&path, &object("{}")).expect("write");
    let mut perms = fs::metadata(&path).expect("meta").permissions();
    perms.set_readonly(true);
    fs::set_permissions(&path, perms).expect("read-only");
    let old = SystemTime::now() - Duration::from_secs(500);
    set_mtime(&path, old);
    assert_eq!(file_times(&path).expect("times").modified, old);
    touch(&path).expect("touch");
    assert!(file_times(&path).expect("times").modified > old);
}

#[cfg(unix)]
#[test]
fn rewrites_keep_a_restricted_config_restricted() {
    use std::os::unix::fs::PermissionsExt;
    let dir = TempDir::new();
    let path = dir.path("pulsar-p.json");
    fs::write(&path, "{\n \"port\": 1\n}").expect("write");
    fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).expect("chmod");
    let old = load_document(&path).expect("load");
    let mut new = old.clone();
    new.set("port", Value::from(2));
    let outcome = commit(&path, &old, new, |_| Value::Null).expect("commit");
    assert!(outcome.prev.is_some());
    let mode = |p: &Path| fs::metadata(p).expect("metadata").permissions().mode() & 0o777;
    assert_eq!(mode(&path), 0o600);
    assert_eq!(mode(&dir.path("pulsar-p.json.prev")), 0o600);
    RunConfigStore::new(&path)
        .update(|d| d.set("port", Value::from(3)))
        .expect("update");
    assert_eq!(mode(&path), 0o600);
    assert!(!dir.path("pulsar-p.json.tmp").exists());
}

#[test]
fn concurrent_writers_never_leave_a_partial_config() {
    let dir = TempDir::new();
    let path = dir.path("pulsar-c.json");
    write_document(&path, &object("{\"n\": 0}")).expect("seed");
    let filler: String = "x".repeat(64 * 1024);
    std::thread::scope(|scope| {
        for t in 0..4 {
            let path = &path;
            let filler = &filler;
            scope.spawn(move || {
                for i in 0..10 {
                    let store = RunConfigStore::new(path);
                    store
                        .update(|d| {
                            d.set("n", Value::from(t * 100 + i));
                            d.set("pad", Value::String(filler.clone()));
                        })
                        .expect("update");
                    let mut doc = object("{}");
                    doc.set("pad", Value::String(filler.clone()));
                    write_document(path, &doc).expect("write");
                }
            });
        }
    });
    let doc = load_document(&path).expect("the config parses after concurrent writes");
    assert!(doc.get("pad").is_some());
    assert!(!dir.path("pulsar-c.json.tmp").exists());
}
