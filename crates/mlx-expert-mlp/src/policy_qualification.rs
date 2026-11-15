//! Source-only qualification adapters shared with the prospective native child.
use crate::{
    resident_fixture::{ensure, Result},
    resident_pipeline::Driver,
    weighted::{
        self,
        staged::{self, Mode, Policy, StagedWeightedExecutor},
        InputStore,
    },
};
use backend::step::StepCoordinator;
use mlx_native_affine::fixture::sha256_hex;
use serde_json::{json, Value};
use std::{
    fs::File,
    io::{Cursor, Write},
    path::Path,
};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Arm {
    pub profile: &'static str,
    pub mode: Mode,
    pub policy: Option<Policy>,
}

impl Arm {
    pub fn parse(profile: &str, mode: &str, policy: Option<&str>) -> Result<Self> {
        let profile = match profile {
            "default" => "default",
            "mixed" => "mixed",
            _ => return Err("unsupported profile".into()),
        };
        let mode = match mode {
            "Serial" => Mode::Serial,
            "Overlap" => Mode::Overlap,
            _ => return Err("unsupported scheduling mode".into()),
        };
        let policy = match policy {
            Some("BufferedRequested") => Some(Policy::BufferedRequested),
            Some("NoCacheRequested") => Some(Policy::NoCacheRequested),
            None => None,
            _ => return Err("unsupported descriptor policy".into()),
        };
        Ok(Self {
            profile,
            mode,
            policy,
        })
    }

    pub fn ordinal(self) -> usize {
        let pair =
            2 * usize::from(self.profile == "mixed") + usize::from(self.mode == Mode::Overlap);
        match self.policy {
            None => pair,
            Some(p) => 2 * pair + usize::from(p == Policy::NoCacheRequested),
        }
    }

    pub fn setup<D: Driver>(
        self,
        root: &Path,
        driver: D,
    ) -> Result<(StepCoordinator<StagedWeightedExecutor<D>>, InputStore)> {
        let book = weighted::RouteBook::fixed(self.profile)?;
        match self.policy {
            Some(p) => {
                staged::setup_with_policy(root, self.profile, book, self.mode, p, driver, None)
            }
            None => staged::setup(root, self.profile, book, self.mode, driver, None),
        }
    }
}

fn lower_hex(v: &Value, count: usize) -> bool {
    v.as_str().is_some_and(|s| {
        s.len() == count && s.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
    })
}

// Checking canonical bytes also rejects duplicate keys at every nesting level before
// their de-duplicated serde_json representation could be used as authority.
fn startup_json(raw: &[u8], pretty: bool) -> Result<Value> {
    ensure(!raw.is_empty() && raw.len() <= 8192, "bounded startup")?;
    let value: Value = serde_json::from_slice(raw).map_err(|e| e.to_string())?;
    let canonical = if pretty {
        serde_json::to_vec_pretty(&value)
    } else {
        serde_json::to_vec(&value)
    }
    .map_err(|e| e.to_string())?;
    // Python's custody codec uses ensure_ascii=True, including UTF-16 surrogate pairs.
    let encoded = std::str::from_utf8(&canonical).map_err(|e| e.to_string())?;
    let mut ascii = Vec::with_capacity(raw.len());
    for c in encoded.chars() {
        if (c as u32) < 127 {
            ascii.push(c as u8);
        } else {
            for unit in c.encode_utf16(&mut [0u16; 2]) {
                write!(ascii, "\\u{unit:04x}").map_err(|e| e.to_string())?;
            }
        }
    }
    ascii.push(b'\n');
    ensure(raw == ascii, "noncanonical startup")?;
    Ok(value)
}

/// The private verifier binds run, source, input and executable identities before it
/// writes startup. Independently check its two byte channels, current page and placement.
pub fn fixed_startup(
    stdout: &[u8],
    saved: &[u8],
    directory: &str,
    page_size: u64,
    intent_sha256: &str,
    reference: &str,
    measured_images: &Value,
) -> Result<(Arm, Value)> {
    let v = startup_json(stdout, false)?;
    ensure(startup_json(saved, true)? == v, "startup channels disagree")?;
    let keys = [
        "schema",
        "run",
        "ordinal",
        "profile",
        "arm",
        "policy",
        "page_size",
        "closure_sha256",
        "input_sha256",
        "reference",
        "intent_sha256",
        "source",
        "tree",
        "binary_sha256",
        "build_sha256",
        "images",
    ];
    ensure(
        v.as_object()
            .is_some_and(|m| m.len() == keys.len() && keys.iter().all(|k| m.contains_key(*k))),
        "strict startup keys",
    )?;
    ensure(
        v["schema"] == "staged-policy-startup/1"
            && v["reference"] == reference
            && v["closure_sha256"] == v["input_sha256"]
            && v["intent_sha256"] == intent_sha256
            && v["images"] == *measured_images
            && matches!(page_size, 4096 | 16384)
            && v["page_size"].as_u64() == Some(page_size),
        "startup identity/page",
    )?;
    for name in [
        "run",
        "closure_sha256",
        "input_sha256",
        "reference",
        "intent_sha256",
        "build_sha256",
        "binary_sha256",
    ] {
        ensure(lower_hex(&v[name], 64), "startup digest")?;
    }
    ensure(
        lower_hex(&v["source"], 40) && lower_hex(&v["tree"], 40),
        "startup git identity",
    )?;
    let text = |k: &str| v[k].as_str().ok_or_else(|| format!("startup string {k}"));
    let arm = Arm::parse(text("profile")?, text("arm")?, Some(text("policy")?))?;
    let ordinal = arm.ordinal();
    ensure(
        v["ordinal"].as_u64() == Some(ordinal as u64)
            && directory
                == format!(
                    "{ordinal}-{}-{}-{}",
                    arm.profile,
                    text("arm")?,
                    text("policy")?
                ),
        "startup arm binding",
    )?;
    Ok((arm, v))
}

pub const HOST_SCHEMA: &str = "staged-policy-host-adapter/1";
pub const NATIVE_SCHEMA: &str = "staged-policy-native-arm/1";
pub const JOURNAL_SLOT: usize = 332_800;
pub const JOURNAL_PAYLOAD: usize = 18 * 36_864 + 5 * 1_024;
pub const PAYLOAD_LIMIT: usize = 2 << 20;
const FAILURE_LIMIT: usize = 8 << 10;
const REPORT_LIMIT: usize = 128 << 10;

/// A fresh arm directory. Every size is checked before opening a file. A failed
/// write keeps its reservation since the OS may already have accepted a prefix.
pub struct ArmFiles<'a> {
    root: &'a Path,
    bytes: usize,
    journal_bytes: usize,
}
impl<'a> ArmFiles<'a> {
    pub fn new(root: &'a Path) -> Self {
        Self {
            root,
            bytes: 0,
            journal_bytes: 0,
        }
    }
    pub fn bytes(&self) -> usize {
        self.bytes
    }

    fn put(&mut self, name: &str, raw: &[u8], limit: usize, available: usize) -> Result<()> {
        let total = self
            .bytes
            .checked_add(raw.len())
            .ok_or("arm size overflow")?;
        ensure(
            raw.len() <= limit && total <= available,
            "arm artifact size",
        )?;
        let mut f = File::create_new(self.root.join(name)).map_err(|e| e.to_string())?;
        self.bytes = total;
        f.write_all(raw)
            .and_then(|_| f.sync_all())
            .map_err(|e| e.to_string())
    }

    pub fn vector(&mut self, pos: u64, raw: &[u8]) -> Result<()> {
        ensure(pos < 5 && raw.len() == 512, "committed vector geometry")?;
        self.put(
            &format!("weighted-{pos}.f32"),
            raw,
            512,
            PAYLOAD_LIMIT - FAILURE_LIMIT,
        )
    }

    pub fn records<D: Driver>(
        &mut self,
        host: &StagedWeightedExecutor<D>,
    ) -> Result<(usize, Vec<Value>)> {
        let mut count = 0;
        for (i, (_, _, raw)) in host.records().enumerate() {
            ensure(i < 12, "occurrence count")?;
            self.put(
                &format!("occ-{i:02}.json"),
                raw,
                32_768,
                PAYLOAD_LIMIT - FAILURE_LIMIT,
            )?;
            count += 1;
        }
        for (i, raw) in host.transport_records().enumerate() {
            ensure(i < 5, "transport count")?;
            self.put(
                &format!("transport-{i}.json"),
                raw,
                staged::TRANSPORT_ROW,
                PAYLOAD_LIMIT - FAILURE_LIMIT,
            )?;
        }
        let mut journals = Vec::new();
        for (i, raw) in host.policy_journal().enumerate() {
            journals.push(self.policy_journal(i, raw)?);
        }
        Ok((count, journals))
    }

    /// Preserve the original joined bytes, including an empty hit array or a failed transfer.
    /// Interpretation of these bytes and native acceptance belong to the independent checker.
    pub fn policy_journal(&mut self, pos: usize, raw: &[u8]) -> Result<Value> {
        let total = self
            .journal_bytes
            .checked_add(raw.len())
            .ok_or("journal bytes overflow")?;
        ensure(
            pos < 5 && total <= JOURNAL_PAYLOAD && raw.len() <= JOURNAL_SLOT,
            "policy journal budget",
        )?;
        self.journal_bytes = total;
        self.put(
            &format!("policy-{pos}.json"),
            raw,
            JOURNAL_SLOT,
            PAYLOAD_LIMIT - FAILURE_LIMIT,
        )?;
        Ok(json!({"bytes":raw.len(),"sha256":sha256_hex(raw)}))
    }

    pub fn report(&mut self, value: &Value) -> Result<()> {
        let mut buffer = vec![0; REPORT_LIMIT];
        let mut dest = Cursor::new(buffer.as_mut_slice());
        serde_json::to_writer(&mut dest, value).map_err(|_| "bounded report encoding")?;
        let size = dest.position() as usize;
        self.put(
            "report.json",
            &buffer[..size],
            REPORT_LIMIT,
            PAYLOAD_LIMIT - FAILURE_LIMIT,
        )
    }

    pub fn failure(&mut self, value: &Value) -> Result<()> {
        let mut buffer = [0; FAILURE_LIMIT];
        let mut dest = Cursor::new(buffer.as_mut_slice());
        serde_json::to_writer(&mut dest, value).map_err(|_| "bounded failure encoding")?;
        let size = dest.position() as usize;
        self.put(
            "failure.json",
            &buffer[..size],
            FAILURE_LIMIT,
            PAYLOAD_LIMIT,
        )
    }
}

pub fn journal_digest<D: Driver>(host: &StagedWeightedExecutor<D>, pos: usize) -> Result<String> {
    let mut journals = host.policy_journal();
    let row = journals.nth(pos).ok_or("missing current policy journal")?;
    ensure(
        journals.next().is_none() && row.len() <= JOURNAL_SLOT,
        "policy journal index",
    )?;
    Ok(sha256_hex(row))
}
