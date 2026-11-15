//! The volatile-field list: `specs/022-console-serving-parity/contracts/volatile-fields.json`.
//!
//! contracts/parity-ledger.md section 1.1 is the rule: everything the server sends is
//! observable unless it is on this list, and each listed field carries a donor citation.
//! The list names generated ids, timestamps and `created` fields, the `Date` header, the
//! value of the `Server` header (approved deviation P-1), timing and rate figures,
//! uptime, process ids, ports and temporary paths. Header names and positions stay
//! observable; of `Date` and `Server` only the values are volatile (tasks.md R29). The
//! normalizer (CNF-04) reads the list and replaces each field by its class placeholder
//! after the class check; this module only reads and checks the file.

use serde_json::Value;

use super::error::{Result, ScenarioError};
use super::json::{self, Obj};

/// The largest volatile-field file, in bytes.
pub const MAX_VOLATILE_BYTES: usize = 256 * 1024;

/// The most fields listed.
pub const MAX_VOLATILE_FIELDS: usize = 512;

/// Members of the top-level object.
pub const LIST_FIELDS: &[&str] = &["title", "rule", "donor_commit", "classes", "fields"];

/// Members of a class description.
pub const CLASS_FIELDS: &[&str] = &["class", "placeholder", "check"];

/// Members of a field.
pub const FIELD_FIELDS: &[&str] = &["id", "class", "location", "donor", "note"];

/// The classes a volatile field can have.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VolatileClass {
    /// A generated id: replaced by `<prefix#k>`, numbered by first appearance.
    Id,
    /// Seconds since the epoch, an integer within the run window.
    EpochS,
    /// Seconds since the epoch as a fraction, within the run window.
    EpochFloat,
    /// An ISO-8601 time stamp.
    Iso,
    /// A duration, rate or other wall-clock figure: a non-negative number.
    Num,
    /// A header value that differs by implementation or by time.
    HeaderValue,
    /// A process id.
    Pid,
    /// A TCP port.
    Port,
    /// A path under the per-scenario temporary directory.
    TmpPath,
}

impl VolatileClass {
    /// Every class, in the order the file documents them.
    pub const ALL: &'static [VolatileClass] = &[
        VolatileClass::Id,
        VolatileClass::EpochS,
        VolatileClass::EpochFloat,
        VolatileClass::Iso,
        VolatileClass::Num,
        VolatileClass::HeaderValue,
        VolatileClass::Pid,
        VolatileClass::Port,
        VolatileClass::TmpPath,
    ];

    /// The class as the file writes it.
    pub fn as_str(self) -> &'static str {
        match self {
            VolatileClass::Id => "id",
            VolatileClass::EpochS => "epoch-s",
            VolatileClass::EpochFloat => "epoch-float",
            VolatileClass::Iso => "iso",
            VolatileClass::Num => "num",
            VolatileClass::HeaderValue => "header-value",
            VolatileClass::Pid => "pid",
            VolatileClass::Port => "port",
            VolatileClass::TmpPath => "tmp-path",
        }
    }

    fn parse(s: &str) -> Option<Self> {
        Self::ALL.iter().copied().find(|c| c.as_str() == s)
    }
}

/// Where a volatile field is found.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Location {
    /// The value of a response header (the name stays observable).
    Header {
        /// The header name, compared case-insensitively.
        name: String,
    },
    /// A member of a JSON object in a body, a stream event, an NDJSON line or a file.
    JsonKey {
        /// The member name.
        key: String,
        /// When given, only a member of an object that is itself the value of this key.
        parent: Option<String>,
        /// When given, only values of this JSON type: `integer`, `number` or `string`.
        value_type: Option<String>,
    },
    /// A string value starting with a fixed prefix followed by lower-case hex digits.
    IdPrefix {
        /// The fixed prefix, such as `chatcmpl-`.
        prefix: String,
        /// How many hex digits follow it.
        hex_digits: u64,
    },
    /// A sample of a Prometheus text-format metric, by metric name.
    Metric {
        /// The metric name.
        name: String,
    },
    /// A file name under the data or temporary directory, with `<pid>`, `<hex>` or
    /// `<port>` holes.
    FileName {
        /// The pattern.
        pattern: String,
    },
    /// Text in a contracted log line, with holes as for file names.
    LogText {
        /// The pattern.
        pattern: String,
    },
}

/// One volatile field.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VolatileField {
    /// A stable id for review and annotations.
    pub id: String,
    /// Its class.
    pub class: VolatileClass,
    /// Where it is found.
    pub location: Location,
    /// Donor citations, each `serve/<file>:<line>` or `serve/<file>:<first>-<last>`.
    pub donor: Vec<String>,
    /// Free text for the reviewer.
    pub note: Option<String>,
}

/// The volatile-field list.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VolatileFields {
    /// The fields, in file order.
    pub fields: Vec<VolatileField>,
}

impl VolatileFields {
    /// Reads and checks a volatile-field list.
    pub fn from_json_str(text: &str) -> Result<Self> {
        let value = json::parse_strict(text, MAX_VOLATILE_BYTES)?;
        let obj = Obj::of(&value, "")?;
        obj.allow_only(LIST_FIELDS)?;
        for key in ["title", "rule", "donor_commit"] {
            if let Some((v, p)) = obj.get(key) {
                json::nonempty_string(v, &p, 2000)?;
            }
        }
        let (cv, cp) = obj.required("classes")?;
        let classes = json::nonempty_array(cv, &cp, VolatileClass::ALL.len())?;
        let mut documented = Vec::new();
        for (i, item) in classes.iter().enumerate() {
            let ip = json::index(&cp, i);
            let o = Obj::of(item, &ip)?;
            o.allow_only(CLASS_FIELDS)?;
            let (v, p) = o.required("class")?;
            let name = json::nonempty_string(v, &p, 32)?;
            let Some(class) = VolatileClass::parse(name) else {
                return Err(ScenarioError::invalid(p, "not a volatile class"));
            };
            if documented.contains(&class) {
                return Err(ScenarioError::invalid(p, "documented twice"));
            }
            for key in ["placeholder", "check"] {
                let (v, p) = o.required(key)?;
                json::nonempty_string(v, &p, 500)?;
            }
            documented.push(class);
        }
        if documented.len() != VolatileClass::ALL.len() {
            return Err(ScenarioError::invalid(cp, "every class must be documented"));
        }

        let (fv, fp) = obj.required("fields")?;
        let mut fields: Vec<VolatileField> = Vec::new();
        for (i, item) in json::nonempty_array(fv, &fp, MAX_VOLATILE_FIELDS)?
            .iter()
            .enumerate()
        {
            let ip = json::index(&fp, i);
            let field = field(item, &ip)?;
            if fields.iter().any(|f| f.id == field.id) {
                return Err(ScenarioError::invalid(
                    json::child(&ip, "id"),
                    "this id is used twice",
                ));
            }
            fields.push(field);
        }
        Ok(Self { fields })
    }

    /// The fields of `class`.
    pub fn of_class(&self, class: VolatileClass) -> impl Iterator<Item = &VolatileField> {
        self.fields.iter().filter(move |f| f.class == class)
    }

    /// Whether the value of header `name` is volatile (case-insensitive).
    pub fn header_value_is_volatile(&self, name: &str) -> bool {
        self.fields.iter().any(
            |f| matches!(&f.location, Location::Header { name: n } if n.eq_ignore_ascii_case(name)),
        )
    }
}

/// `serve/<path>:<line>` or `serve/<path>:<first>-<last>`, lines from 1, first before
/// last.
pub(crate) fn is_donor_citation(s: &str) -> bool {
    let Some((path, lines)) = s.rsplit_once(':') else {
        return false;
    };
    let path_ok = path.strip_prefix("serve/").is_some_and(|rest| {
        !rest.is_empty()
            && !rest
                .split('/')
                .any(|seg| seg.is_empty() || seg == "." || seg == "..")
            && rest
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'.' | b'/' | b'-'))
    });
    let line = |t: &str| -> Option<u64> {
        if t.is_empty() || !t.bytes().all(|b| b.is_ascii_digit()) || t.starts_with('0') {
            return None;
        }
        t.parse().ok()
    };
    let lines_ok = match lines.split_once('-') {
        Some((a, b)) => matches!((line(a), line(b)), (Some(x), Some(y)) if x < y),
        None => line(lines).is_some(),
    };
    path_ok && lines_ok
}

fn field(v: &Value, p: &str) -> Result<VolatileField> {
    let o = Obj::of(v, p)?;
    o.allow_only(FIELD_FIELDS)?;
    let (v, ip) = o.required("id")?;
    let id = json::nonempty_string(v, &ip, 64)?;
    if !id
        .bytes()
        .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
    {
        return Err(ScenarioError::invalid(ip, "must be made of [a-z0-9-]"));
    }
    let (v, cp) = o.required("class")?;
    let Some(class) = VolatileClass::parse(json::nonempty_string(v, &cp, 32)?) else {
        return Err(ScenarioError::invalid(cp, "not a volatile class"));
    };
    let (v, lp) = o.required("location")?;
    let location = location(v, &lp)?;
    let (v, dp) = o.required("donor")?;
    let mut donor = Vec::new();
    for (i, item) in json::nonempty_array(v, &dp, 16)?.iter().enumerate() {
        let cp = json::index(&dp, i);
        let s = json::nonempty_string(item, &cp, 256)?;
        if !is_donor_citation(s) {
            return Err(ScenarioError::invalid(
                cp,
                "a donor citation is serve/<file>:<line> or serve/<file>:<first>-<last>",
            ));
        }
        donor.push(s.to_string());
    }
    let note = match o.get("note") {
        Some((v, p)) => Some(json::nonempty_string(v, &p, 2000)?.to_string()),
        None => None,
    };
    Ok(VolatileField {
        id: id.to_string(),
        class,
        location,
        donor,
        note,
    })
}

fn location(v: &Value, p: &str) -> Result<Location> {
    let o = Obj::of(v, p)?;
    let (kv, kp) = o.required("kind")?;
    let text = |key: &'static str| -> Result<String> {
        let (v, p) = o.required(key)?;
        Ok(json::nonempty_string(v, &p, 256)?.to_string())
    };
    match json::string(kv, &kp, 32)? {
        "header" => {
            o.allow_only(&["kind", "name"])?;
            Ok(Location::Header {
                name: text("name")?,
            })
        }
        "json-key" => {
            o.allow_only(&["kind", "key", "parent", "value_type"])?;
            let parent = match o.get("parent") {
                Some((v, p)) => Some(json::nonempty_string(v, &p, 256)?.to_string()),
                None => None,
            };
            let value_type = match o.get("value_type") {
                Some((v, p)) => {
                    let t = json::string(v, &p, 16)?;
                    if !matches!(t, "integer" | "number" | "string") {
                        return Err(ScenarioError::invalid(
                            p,
                            "must be \"integer\", \"number\" or \"string\"",
                        ));
                    }
                    Some(t.to_string())
                }
                None => None,
            };
            Ok(Location::JsonKey {
                key: text("key")?,
                parent,
                value_type,
            })
        }
        "id-prefix" => {
            o.allow_only(&["kind", "prefix", "hex_digits"])?;
            let (v, hp) = o.required("hex_digits")?;
            Ok(Location::IdPrefix {
                prefix: text("prefix")?,
                hex_digits: json::uint(v, &hp, 1, 64)?,
            })
        }
        "metric" => {
            o.allow_only(&["kind", "name"])?;
            Ok(Location::Metric {
                name: text("name")?,
            })
        }
        "file-name" => {
            o.allow_only(&["kind", "pattern"])?;
            Ok(Location::FileName {
                pattern: text("pattern")?,
            })
        }
        "log-text" => {
            o.allow_only(&["kind", "pattern"])?;
            Ok(Location::LogText {
                pattern: text("pattern")?,
            })
        }
        _ => Err(ScenarioError::invalid(
            kp,
            "must be header, json-key, id-prefix, metric, file-name or log-text",
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn classes() -> String {
        VolatileClass::ALL
            .iter()
            .map(|c| {
                format!(
                    r#"{{"class": "{}", "placeholder": "<x>", "check": "y"}}"#,
                    c.as_str()
                )
            })
            .collect::<Vec<_>>()
            .join(", ")
    }

    fn list(fields: &str) -> Result<VolatileFields> {
        VolatileFields::from_json_str(&format!(
            r#"{{"classes": [{}], "fields": [{fields}]}}"#,
            classes()
        ))
    }

    #[test]
    fn a_minimal_list_loads() {
        let l = list(
            r#"{"id": "header-date", "class": "header-value",
                "location": {"kind": "header", "name": "Date"}, "donor": ["serve/server.py:5459"]},
               {"id": "chat-id", "class": "id",
                "location": {"kind": "id-prefix", "prefix": "chatcmpl-", "hex_digits": 24},
                "donor": ["serve/server.py:4936"]}"#,
        )
        .unwrap();
        assert!(l.header_value_is_volatile("date"));
        assert!(!l.header_value_is_volatile("Content-Type"));
        assert_eq!(l.of_class(VolatileClass::Id).count(), 1);
    }

    #[test]
    fn citations_are_checked() {
        for ok in [
            "serve/server.py:1",
            "serve/server.py:10-20",
            "serve/web/app.js:5",
        ] {
            assert!(is_donor_citation(ok), "{ok}");
        }
        for bad in [
            "server.py:1",
            "serve/server.py",
            "serve/server.py:0",
            "serve/server.py:20-10",
            "serve/../x.py:1",
            "serve/server.py:01",
            "serve/:3",
        ] {
            assert!(!is_donor_citation(bad), "{bad}");
        }
        let err = list(
            r#"{"id": "a", "class": "num", "location": {"kind": "metric", "name": "m"},
                "donor": ["Python stdlib"]}"#,
        )
        .unwrap_err();
        assert_eq!(err.pointer, "/fields/0/donor/0");
    }

    #[test]
    fn every_class_must_be_documented() {
        let err = VolatileFields::from_json_str(
            r#"{"classes": [{"class": "id", "placeholder": "<x>", "check": "y"}],
                "fields": []}"#,
        )
        .unwrap_err();
        assert_eq!(err.pointer, "/classes");
    }

    #[test]
    fn bad_locations_and_duplicates_are_refused() {
        let err = list(
            r#"{"id": "a", "class": "num", "location": {"kind": "json-key", "key": "k", "value_type": "bool"},
                "donor": ["serve/server.py:1"]}"#,
        )
        .unwrap_err();
        assert_eq!(err.pointer, "/fields/0/location/value_type");
        let err = list(
            r#"{"id": "a", "class": "num", "location": {"kind": "elsewhere"}, "donor": ["serve/server.py:1"]}"#,
        )
        .unwrap_err();
        assert_eq!(err.pointer, "/fields/0/location/kind");
        let one = r#"{"id": "a", "class": "num", "location": {"kind": "metric", "name": "m"}, "donor": ["serve/server.py:1"]}"#;
        let err = list(&format!("{one}, {one}")).unwrap_err();
        assert_eq!(err.pointer, "/fields/1/id");
        let err = list(
            r#"{"id": "a", "class": "later", "location": {"kind": "metric", "name": "m"}, "donor": ["serve/server.py:1"]}"#,
        )
        .unwrap_err();
        assert_eq!(err.pointer, "/fields/0/class");
    }
}
