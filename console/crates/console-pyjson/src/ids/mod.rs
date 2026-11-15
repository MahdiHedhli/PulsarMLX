//! Owned by API-01. Random lowercase hexadecimal ids drawn from operating-system
//! randomness.
//!
//! The donor makes every id from `uuid.uuid4().hex`: `"chatcmpl-" + hex[:24]`,
//! `"msg_" + hex[:24]`, `"call_" + hex[:24]` and the Responses ids `resp_`, `item_`, `rs_`
//! and `fc_`, and `hex[:12]` for request file names. A version-4 UUID is 122 random bits with
//! the version nibble `4` at hex position 12 and a variant nibble in `8`, `9`, `a` or `b` at
//! position 16, so a donor id of 24 characters always carries both. [`uuid4_hex`] reproduces
//! that layout from operating-system randomness without the `uuid` crate (tasks.md R8):
//! `getentropy(2)` where the C library has it, `/dev/urandom` on other Unix systems.
//!
//! Behavior reference: project-maya serve/server.py:4936 and 5251, serve/frontend.py:805,
//! serve/responses.py:133, 354 and 412-418 at 7e68a30f.

use std::fmt;

/// The longest hexadecimal string [`random_hex`] produces (an explicit bound on the size a
/// caller can ask for).
pub const MAX_HEX_LEN: usize = 4096;

/// `getentropy(2)` refuses more than 256 bytes per call.
const GETENTROPY_MAX: usize = 256;

/// Prefix of a Chat Completions id (`chatcmpl-` + 24 hex characters).
pub const CHAT_COMPLETION_PREFIX: &str = "chatcmpl-";
/// Prefix of an Anthropic message id and of a Responses message item id.
pub const MESSAGE_PREFIX: &str = "msg_";
/// Prefix of a tool call id.
pub const CALL_PREFIX: &str = "call_";
/// Prefix of a Responses response id.
pub const RESPONSE_PREFIX: &str = "resp_";
/// Prefix of a Responses input item id.
pub const ITEM_PREFIX: &str = "item_";
/// Prefix of a Responses reasoning item id.
pub const REASONING_PREFIX: &str = "rs_";
/// Prefix of a Responses function call item id.
pub const FUNCTION_CALL_PREFIX: &str = "fc_";

/// Why no random id could be made.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum IdError {
    /// The operating system refused to provide randomness; holds `errno`.
    Os(i32),
    /// Reading `/dev/urandom` failed (on a Unix system without `getentropy`).
    Device(String),
    /// This platform has no source of randomness that this crate reads.
    Unsupported,
    /// More than [`MAX_HEX_LEN`] characters were asked for.
    TooLong(usize),
}

impl fmt::Display for IdError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            IdError::Os(errno) => write!(f, "operating-system randomness failed (errno {errno})"),
            IdError::Device(why) => write!(f, "reading /dev/urandom failed: {why}"),
            IdError::Unsupported => f.write_str("no operating-system randomness on this platform"),
            IdError::TooLong(n) => write!(
                f,
                "{n} hex characters asked for; the limit is {MAX_HEX_LEN}"
            ),
        }
    }
}

impl std::error::Error for IdError {}

/// One `getentropy` call filling `buf` (at most 256 bytes).
#[cfg(any(
    target_vendor = "apple",
    all(target_os = "linux", target_env = "gnu"),
    target_os = "android",
    target_os = "freebsd",
    target_os = "openbsd",
    target_os = "netbsd"
))]
fn os_fill_chunk(buf: &mut [u8]) -> Result<(), IdError> {
    // SAFETY: `buf` is a valid, writable, exclusively borrowed region of `buf.len()` bytes
    // for the whole call, and `getentropy` writes at most `buflen` bytes into it.
    let rc = unsafe { libc::getentropy(buf.as_mut_ptr().cast::<libc::c_void>(), buf.len()) };
    if rc == 0 {
        Ok(())
    } else {
        Err(IdError::Os(
            std::io::Error::last_os_error().raw_os_error().unwrap_or(0),
        ))
    }
}

/// `/dev/urandom` on a Unix system whose C library has no `getentropy` in `libc`.
#[cfg(all(
    unix,
    not(any(
        target_vendor = "apple",
        all(target_os = "linux", target_env = "gnu"),
        target_os = "android",
        target_os = "freebsd",
        target_os = "openbsd",
        target_os = "netbsd"
    ))
))]
fn os_fill_chunk(buf: &mut [u8]) -> Result<(), IdError> {
    use std::io::Read;
    if buf.len() > GETENTROPY_MAX {
        return Err(IdError::Os(libc::EIO));
    }
    std::fs::File::open("/dev/urandom")
        .and_then(|mut f| f.read_exact(buf))
        .map_err(|e| IdError::Device(e.to_string()))
}

#[cfg(not(unix))]
fn os_fill_chunk(_buf: &mut [u8]) -> Result<(), IdError> {
    Err(IdError::Unsupported)
}

/// Fills `buf` with operating-system randomness, 256 bytes per call.
pub fn fill_random(buf: &mut [u8]) -> Result<(), IdError> {
    for chunk in buf.chunks_mut(GETENTROPY_MAX) {
        os_fill_chunk(chunk)?;
    }
    Ok(())
}

const HEX: &[u8; 16] = b"0123456789abcdef";

fn hex_of(bytes: &[u8], n: usize) -> String {
    let mut out = String::with_capacity(n);
    for b in bytes {
        for nibble in [b >> 4, b & 0xf] {
            if out.len() == n {
                return out;
            }
            out.push(char::from(
                HEX.get(usize::from(nibble)).copied().unwrap_or(b'0'),
            ));
        }
    }
    out
}

/// `n` random lowercase hexadecimal characters from `fill`.
fn random_hex_from(
    n: usize,
    fill: &mut dyn FnMut(&mut [u8]) -> Result<(), IdError>,
) -> Result<String, IdError> {
    if n > MAX_HEX_LEN {
        return Err(IdError::TooLong(n));
    }
    let mut bytes = vec![0u8; n.div_ceil(2)];
    fill(&mut bytes)?;
    Ok(hex_of(&bytes, n))
}

/// The 32 hexadecimal characters of a version-4 UUID (Python `uuid.uuid4().hex`) from
/// `fill`.
fn uuid4_hex_from(
    fill: &mut dyn FnMut(&mut [u8]) -> Result<(), IdError>,
) -> Result<String, IdError> {
    let mut bytes = [0u8; 16];
    fill(&mut bytes)?;
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    Ok(hex_of(&bytes, 32))
}

/// `n` random lowercase hexadecimal characters from operating-system randomness.
pub fn random_hex(n: usize) -> Result<String, IdError> {
    random_hex_from(n, &mut fill_random)
}

/// Python `uuid.uuid4().hex`: 32 lowercase hexadecimal characters with the version nibble
/// `4` at position 12 and the variant nibble (`8` to `b`) at position 16.
pub fn uuid4_hex() -> Result<String, IdError> {
    uuid4_hex_from(&mut fill_random)
}

/// `uuid.uuid4().hex[:24]`, the random part of every donor id.
pub fn hex24() -> Result<String, IdError> {
    let mut hex = uuid4_hex()?;
    hex.truncate(24);
    Ok(hex)
}

/// `uuid.uuid4().hex[:12]`, used in request file names.
pub fn hex12() -> Result<String, IdError> {
    let mut hex = uuid4_hex()?;
    hex.truncate(12);
    Ok(hex)
}

/// `prefix + uuid.uuid4().hex[:24]`.
pub fn prefixed_id(prefix: &str) -> Result<String, IdError> {
    Ok(format!("{prefix}{}", hex24()?))
}

/// A Chat Completions id: `chatcmpl-` + 24 hex characters.
pub fn chatcmpl_id() -> Result<String, IdError> {
    prefixed_id(CHAT_COMPLETION_PREFIX)
}

/// An Anthropic message id: `msg_` + 24 hex characters.
pub fn msg_id() -> Result<String, IdError> {
    prefixed_id(MESSAGE_PREFIX)
}

/// A tool call id: `call_` + 24 hex characters.
pub fn call_id() -> Result<String, IdError> {
    prefixed_id(CALL_PREFIX)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn is_lower_hex(s: &str) -> bool {
        s.bytes().all(|c| matches!(c, b'0'..=b'9' | b'a'..=b'f'))
    }

    #[test]
    fn ids_have_the_donor_shape() {
        let id = chatcmpl_id().unwrap_or_default();
        assert_eq!(id.len(), 9 + 24);
        assert!(id.starts_with("chatcmpl-"));
        let hex = &id[9..];
        assert!(is_lower_hex(hex));
        assert_eq!(&hex[12..13], "4");
        assert!(matches!(&hex[16..17], "8" | "9" | "a" | "b"));
        assert!(msg_id().unwrap_or_default().starts_with("msg_"));
        assert_eq!(call_id().unwrap_or_default().len(), 5 + 24);
        assert_eq!(hex12().unwrap_or_default().len(), 12);
        let full = uuid4_hex().unwrap_or_default();
        assert_eq!(full.len(), 32);
        assert!(is_lower_hex(&full));
    }

    #[test]
    fn ids_differ() {
        let a = hex24().unwrap_or_default();
        let b = hex24().unwrap_or_default();
        assert_eq!(a.len(), 24);
        assert_ne!(a, b);
    }

    #[test]
    fn random_hex_lengths() {
        for n in [0usize, 1, 2, 7, 24, 600] {
            let h = random_hex(n).unwrap_or_else(|_| "x".into());
            assert_eq!(h.len(), n);
            assert!(is_lower_hex(&h));
        }
        assert_eq!(
            random_hex(MAX_HEX_LEN + 1),
            Err(IdError::TooLong(MAX_HEX_LEN + 1))
        );
    }

    #[test]
    fn layout_is_deterministic_for_a_fixed_source() {
        let mut fill = |buf: &mut [u8]| -> Result<(), IdError> {
            for (i, b) in buf.iter_mut().enumerate() {
                *b = 0xff - i as u8;
            }
            Ok(())
        };
        assert_eq!(
            uuid4_hex_from(&mut fill).unwrap_or_default(),
            "fffefdfcfbfa49f8b7f6f5f4f3f2f1f0"
        );
        assert_eq!(random_hex_from(5, &mut fill).unwrap_or_default(), "fffef");
    }

    #[test]
    fn source_failure_is_reported() {
        let mut failing = |_: &mut [u8]| -> Result<(), IdError> { Err(IdError::Os(5)) };
        assert_eq!(random_hex_from(24, &mut failing), Err(IdError::Os(5)));
        assert_eq!(uuid4_hex_from(&mut failing), Err(IdError::Os(5)));
        assert_eq!(
            IdError::Os(5).to_string(),
            "operating-system randomness failed (errno 5)"
        );
    }

    #[cfg(unix)]
    #[test]
    fn the_os_call_fails_closed_above_its_limit() {
        // getentropy refuses more than 256 bytes in one call (EIO on Linux and macOS); the
        // error path of the real system call is taken and reported, not ignored.
        let mut big = vec![0u8; GETENTROPY_MAX + 1];
        let result = os_fill_chunk(&mut big);
        assert!(
            matches!(result, Err(IdError::Os(errno)) if errno != 0),
            "{result:?}"
        );
        // fill_random splits the same request into permitted calls.
        assert_eq!(fill_random(&mut big), Ok(()));
    }
}
