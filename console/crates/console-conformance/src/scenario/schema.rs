//! The object shapes of the scenario format, as the loader enforces them.
//!
//! `specs/022-console-serving-parity/contracts/conformance-scenario.schema.json` documents
//! the format for readers and editors; the loader in this module enforces it in code
//! (binding decision B6: no `jsonschema` crate). This table is the single list of member
//! names the loader accepts and requires for each object. A test reads the schema file
//! and fails when one of its `$defs` disagrees with this table, so the two cannot drift.

/// One object shape of the scenario format.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SchemaObject {
    /// Its name under `$defs` in the schema file.
    pub name: &'static str,
    /// Every member it may hold, in the order the schema documents them.
    pub properties: &'static [&'static str],
    /// The members it must hold.
    pub required: &'static [&'static str],
}

/// The top-level scenario object.
pub const SCENARIO: SchemaObject = SchemaObject {
    name: "scenario",
    properties: &[
        "id",
        "description",
        "donor",
        "notes",
        "engine",
        "template",
        "server",
        "steps",
        "observe",
    ],
    required: &["id", "engine", "template", "steps", "observe"],
};

/// The in-process scripted engine.
pub const ENGINE_MOCK: SchemaObject = SchemaObject {
    name: "engine_mock",
    properties: &[
        "kind",
        "tokenizer",
        "script",
        "max_context",
        "info",
        "delay_ms",
        "tok_s",
    ],
    required: &["kind", "tokenizer", "script"],
};

/// A line-protocol fake engine.
pub const ENGINE_LINE: SchemaObject = SchemaObject {
    name: "engine_line",
    properties: &["kind", "fake", "tokenizer", "args", "env"],
    required: &["kind", "fake", "tokenizer"],
};

/// The byte tokenizer: one id per UTF-8 byte, specials from 256.
pub const TOKENIZER_BYTE: SchemaObject = SchemaObject {
    name: "tokenizer_byte",
    properties: &["kind", "extra_specials"],
    required: &["kind"],
};

/// The byte-level BPE tokenizer generated at run time.
pub const TOKENIZER_BPE_BYTES: SchemaObject = SchemaObject {
    name: "tokenizer_bpe_bytes",
    properties: &["kind", "added"],
    required: &["kind"],
};

/// A script entry written as one string repeated.
pub const SCRIPT_REPEAT: SchemaObject = SchemaObject {
    name: "script_repeat",
    properties: &["repeat", "times"],
    required: &["repeat", "times"],
};

/// How the server under test is started.
pub const SERVER: SchemaObject = SchemaObject {
    name: "server",
    properties: &["flags", "env", "config", "data_dir"],
    required: &[],
};

/// One step of a scenario.
pub const STEP: SchemaObject = SchemaObject {
    name: "step",
    properties: &[
        "request",
        "disconnect_after_events",
        "disconnect_after_bytes",
        "wait_for_engine_step",
        "release_engine_step",
        "concurrent_group",
        "signal",
    ],
    required: &[],
};

/// A request described field by field.
pub const REQUEST: SchemaObject = SchemaObject {
    name: "request",
    properties: &[
        "method",
        "path",
        "headers",
        "body",
        "body_text",
        "body_file",
        "http_version",
    ],
    required: &["method", "path"],
};

/// A request written out as raw bytes of text.
pub const REQUEST_RAW: SchemaObject = SchemaObject {
    name: "request_raw",
    properties: &["raw"],
    required: &["raw"],
};

/// What a scenario observes.
pub const OBSERVE: SchemaObject = SchemaObject {
    name: "observe",
    properties: &["http", "engine_tape", "files", "log", "exit"],
    required: &[],
};

/// Every object shape, in the order the schema file lists its `$defs`.
pub const SCHEMA_OBJECTS: &[SchemaObject] = &[
    SCENARIO,
    ENGINE_MOCK,
    ENGINE_LINE,
    TOKENIZER_BYTE,
    TOKENIZER_BPE_BYTES,
    SCRIPT_REPEAT,
    SERVER,
    STEP,
    REQUEST,
    REQUEST_RAW,
    OBSERVE,
];

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn required_members_are_listed_properties_and_names_are_unique() {
        let mut names = std::collections::HashSet::new();
        for object in SCHEMA_OBJECTS {
            assert!(names.insert(object.name), "{} twice", object.name);
            for required in object.required {
                assert!(
                    object.properties.contains(required),
                    "{}: {required} required but not a property",
                    object.name
                );
            }
        }
    }
}
