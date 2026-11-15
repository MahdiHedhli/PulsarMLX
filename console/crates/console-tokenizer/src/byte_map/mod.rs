//! Owned by PRM-04. The GPT-2 byte-to-unicode table, in the donor's order.
//!
//! Byte-level BPE maps each byte to one printable character so that any UTF-8 input can be
//! represented without an unknown token. Bytes `0x21..=0x7E`, `0xA1..=0xAC` and
//! `0xAE..=0xFF` map to the character with the same code point; the other 68 bytes (space,
//! newline, the C0 controls, DEL and the invisible high range) map to `U+0100 + n`, numbered
//! in increasing byte order. The order of the table matters: a vocabulary built from it lists
//! the 256 byte characters in this order, so a wrong order changes every token id.
//!
//! Behavior reference: project-maya tools/strata_tokenizer.py:25-44 at 7e68a30f.

/// Number of bytes that map to a shifted character (`U+0100` and up).
const SHIFTED: usize = 68;

/// The bytes in the donor's dictionary order, and each byte's character.
struct Table {
    /// Byte values in the order `bytes_to_unicode()` inserts them.
    order: [u8; 256],
    /// Character code point for each byte value.
    to_char: [u32; 256],
    /// Byte value for each shifted character `U+0100 + n`.
    from_shifted: [u8; SHIFTED],
}

const fn keeps_own_code_point(b: u8) -> bool {
    (b >= 0x21 && b <= 0x7E) || (b >= 0xA1 && b <= 0xAC) || b >= 0xAE
}

const fn build() -> Table {
    let mut order = [0u8; 256];
    let mut to_char = [0u32; 256];
    let mut from_shifted = [0u8; SHIFTED];
    let mut len = 0usize;
    // The bytes that keep their own code point, in increasing order (three ranges).
    let mut b = 0usize;
    while b < 256 {
        if keeps_own_code_point(b as u8) {
            order[len] = b as u8;
            to_char[b] = b as u32;
            len += 1;
        }
        b += 1;
    }
    // The others, appended in increasing byte order as 256 + n.
    let mut n = 0usize;
    b = 0;
    while b < 256 {
        if !keeps_own_code_point(b as u8) {
            order[len] = b as u8;
            to_char[b] = 256 + n as u32;
            from_shifted[n] = b as u8;
            len += 1;
            n += 1;
        }
        b += 1;
    }
    Table {
        order,
        to_char,
        from_shifted,
    }
}

static TABLE: Table = build();

/// The character byte `b` maps to.
pub fn byte_to_char(b: u8) -> char {
    // Every entry is below U+0144, so the conversion cannot fail; U+FFFD is unreachable.
    char::from_u32(TABLE.to_char[usize::from(b)]).unwrap_or('\u{FFFD}')
}

/// The byte a character of the byte alphabet stands for, or `None` for a character outside
/// the alphabet.
pub fn char_to_byte(c: char) -> Option<u8> {
    let cp = u32::from(c);
    if cp < 256 {
        let b = cp as u8;
        return keeps_own_code_point(b).then_some(b);
    }
    let n = usize::try_from(cp - 256).ok()?;
    TABLE.from_shifted.get(n).copied()
}

/// The whole table as `(byte, character)` pairs in the donor's dictionary order (the order
/// of `BYTE_TO_UNICODE.items()`).
pub fn bytes_to_unicode() -> Vec<(u8, char)> {
    TABLE.order.iter().map(|&b| (b, byte_to_char(b))).collect()
}

/// The 256 characters of the alphabet in the donor's order (`list(BYTE_TO_UNICODE.values())`),
/// which is how a synthetic vocabulary starts.
pub fn alphabet() -> Vec<char> {
    TABLE.order.iter().map(|&b| byte_to_char(b)).collect()
}

/// Maps raw bytes to their byte-level string (`"".join(BYTE_TO_UNICODE[b] for b in raw)`).
pub fn map_bytes(raw: &[u8]) -> String {
    raw.iter().map(|&b| byte_to_char(b)).collect()
}

/// Maps a byte-level string back to bytes. On a character outside the alphabet, returns that
/// character as the error.
pub fn unmap(s: &str) -> Result<Vec<u8>, char> {
    s.chars().map(|c| char_to_byte(c).ok_or(c)).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn printable_bytes_keep_their_code_point() {
        for b in (0x21u8..=0x7E).chain(0xA1..=0xAC).chain(0xAE..=0xFF) {
            assert_eq!(u32::from(byte_to_char(b)), u32::from(b));
        }
    }

    #[test]
    fn shifted_bytes_hand_computed() {
        // 0..=32 take U+0100..=U+0120, then 127, then 128..=160, then 173.
        assert_eq!(byte_to_char(0x00), '\u{0100}');
        assert_eq!(byte_to_char(b'\n'), '\u{010A}');
        assert_eq!(byte_to_char(b' '), '\u{0120}');
        assert_eq!(byte_to_char(0x7F), '\u{0121}');
        assert_eq!(byte_to_char(0x80), '\u{0122}');
        assert_eq!(byte_to_char(0xA0), '\u{0142}');
        assert_eq!(byte_to_char(0xAD), '\u{0143}');
    }

    #[test]
    fn order_is_the_donor_dict_order() {
        let table = bytes_to_unicode();
        assert_eq!(table.len(), 256);
        assert_eq!(table.first(), Some(&(0x21, '!')));
        // 94 + 12 + 82 = 188 bytes keep their code point, then the 68 shifted ones.
        assert_eq!(table.get(187), Some(&(0xFF, '\u{FF}')));
        assert_eq!(table.get(188), Some(&(0x00, '\u{0100}')));
        assert_eq!(table.get(255), Some(&(0xAD, '\u{0143}')));
        let chars = alphabet();
        assert_eq!(chars.len(), 256);
        let mut sorted = chars.clone();
        sorted.sort_unstable();
        sorted.dedup();
        assert_eq!(sorted.len(), 256, "the table is a bijection");
    }

    #[test]
    fn round_trip_every_byte() {
        let all: Vec<u8> = (0u8..=255).collect();
        let mapped = map_bytes(&all);
        assert_eq!(unmap(&mapped), Ok(all));
        assert_eq!(char_to_byte('\u{0144}'), None);
        assert_eq!(char_to_byte(' '), None);
        assert_eq!(char_to_byte('\u{AD}'), None);
        assert_eq!(unmap("a\u{4E00}"), Err('\u{4E00}'));
    }
}
