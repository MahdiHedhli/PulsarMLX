//! Owned by API-03. Lowercase hexadecimal SHA-256, shared by the response owner id and the
//! Responses store.
//!
//! The donor hashes with Python's `hashlib.sha256(data).hexdigest()`: 64 lowercase
//! hexadecimal digits. The response owner id of an authenticated client is that digest of
//! the presented API key's UTF-8 bytes (`console_http::guard`), and the Responses store keys
//! its records by it, so both must produce the same text. Lead decision LD32 puts the helper
//! here, in the crate every other one depends on; the digest itself comes from the `sha2`
//! crate.
//!
//! Behavior reference: project-maya serve/server.py:5821-5826 at 7e68a30f.

use sha2::{Digest, Sha256};

/// The length of [`sha256_hex`]'s result, in characters.
pub const SHA256_HEX_LEN: usize = 64;

/// The SHA-256 digest of `data`, as 32 bytes.
pub fn sha256(data: &[u8]) -> [u8; 32] {
    Sha256::digest(data).into()
}

/// The SHA-256 digest of `data` as 64 lowercase hexadecimal digits, as Python's
/// `hashlib.sha256(data).hexdigest()` writes it.
pub fn sha256_hex(data: &[u8]) -> String {
    to_hex(&sha256(data))
}

/// Bytes as lowercase hexadecimal digits, two per byte (Python's `bytes.hex()`).
pub fn to_hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len().saturating_mul(2));
    for &b in bytes {
        out.push(char::from(DIGITS[usize::from(b >> 4)]));
        out.push(char::from(DIGITS[usize::from(b & 0x0f)]));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    // Test vectors from FIPS 180-4 (the "abc" and two-block messages) and the well-known
    // digest of the empty message.
    #[test]
    fn known_vectors() {
        assert_eq!(
            sha256_hex(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
        assert_eq!(
            sha256_hex(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
        assert_eq!(
            sha256_hex(b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"),
            "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"
        );
    }

    #[test]
    fn a_million_letters_a() {
        let data = vec![b'a'; 1_000_000];
        assert_eq!(
            sha256_hex(&data),
            "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"
        );
    }

    #[test]
    fn hex_is_lowercase_and_two_digits_per_byte() {
        assert_eq!(to_hex(&[0x00, 0x0f, 0xa0, 0xff]), "000fa0ff");
        assert_eq!(to_hex(&[]), "");
        let digest = sha256_hex("k\u{e9}y".as_bytes());
        assert_eq!(digest.len(), SHA256_HEX_LEN);
        assert!(digest
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)));
        assert_eq!(sha256(b"abc").len(), 32);
    }
}
