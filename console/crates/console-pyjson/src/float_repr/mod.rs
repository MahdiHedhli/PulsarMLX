//! Owned by API-01. Python float `repr`: shortest round-trip digits and the exponent form.
//!
//! Python 3 writes a float with the shortest decimal digit string that reads back to the same
//! double (`float_repr_style == 'short'`), and chooses between two layouts by the decimal
//! point position `decpt` (the value is `0.DIGITS * 10**decpt`):
//!
//! - fixed notation when `-4 < decpt <= 16`, with `.0` added to an integral value
//!   (`2.0`, `123456789.0`, `0.0001`);
//! - exponent notation otherwise, with the exponent signed and at least two digits wide and no
//!   `.0` added (`1e-05`, `1e+16`, `1.5e+300`, `5e-324`).
//!
//! `str(x)` is the same as `repr(x)` for a float, so the same function backs the Prometheus
//! value rendering. JSON writes the non-finite values as `NaN`, `Infinity` and `-Infinity`
//! (see [`json_float`]); `repr` writes them as `nan`, `inf` and `-inf`.
//!
//! The digit string comes from Rust's own shortest round-trip formatting (`{:e}`), which, like
//! CPython's `dtoa`, yields the shortest digit string that rounds back to the same value and,
//! among those, the one closest to it. Only the layout is ported.
//!
//! Behavior reference: CPython `Python/pystrtod.c` (`format_float_short`, mode `'r'`) as
//! observed through `repr(float)`; used by project-maya serve/server.py:5457-5463 at 7e68a30f
//! through `json.dumps`.

/// Shortest round-trip decimal digits of a finite, non-zero magnitude, with the decimal point
/// position: the value is `0.DIGITS * 10**decpt`.
///
/// Returns `("0", 1)` for zero (both signs), which is how `repr` lays out `0.0`.
fn shortest_digits(magnitude: f64) -> (String, i32) {
    if magnitude == 0.0 {
        return (String::from("0"), 1);
    }
    // `{:e}` gives `d[.ddd]e<exp>` with the shortest round-trip digit count. When two digit
    // strings of that length both round-trip and the value lies exactly between them, Rust's
    // shortest mode may pick the upper one, while CPython picks the one a correct
    // round-half-even rounding gives (repr(1689376348324154.25) is '1689376348324154.2').
    // Rust's exact mode (`{:.Ne}`) rounds half to even, so the digits are taken from it at
    // the shortest length: the correctly rounded string of that length is the closest one,
    // and so it round-trips too.
    let shortest = format!("{:e}", magnitude);
    let count = shortest
        .split('e')
        .next()
        .unwrap_or("")
        .chars()
        .filter(char::is_ascii_digit)
        .count()
        .max(1);
    let text = format!("{:.*e}", count - 1, magnitude);
    let (mantissa, exponent) = match text.split_once('e') {
        Some(parts) => parts,
        None => (text.as_str(), "0"),
    };
    let digits: String = mantissa.chars().filter(|c| c.is_ascii_digit()).collect();
    let exp: i32 = exponent.parse().unwrap_or(0);
    // Strip trailing zeros (Rust never writes them, but keep the invariant explicit).
    let trimmed = digits.trim_end_matches('0');
    let digits = if trimmed.is_empty() {
        String::from("0")
    } else {
        trimmed.to_string()
    };
    (digits, exp + 1)
}

/// Python `repr(x)` (and `str(x)`) for a float.
///
/// ```
/// use console_pyjson::float_repr::repr_f64;
/// assert_eq!(repr_f64(0.1), "0.1");
/// assert_eq!(repr_f64(1e-5), "1e-05");
/// assert_eq!(repr_f64(1e16), "1e+16");
/// assert_eq!(repr_f64(2.0), "2.0");
/// assert_eq!(repr_f64(-0.0), "-0.0");
/// assert_eq!(repr_f64(f64::NAN), "nan");
/// ```
pub fn repr_f64(x: f64) -> String {
    if x.is_nan() {
        return String::from("nan");
    }
    if x.is_infinite() {
        return String::from(if x > 0.0 { "inf" } else { "-inf" });
    }
    let mut out = String::new();
    if x.is_sign_negative() {
        out.push('-');
    }
    let (digits, decpt) = shortest_digits(x.abs());
    let ndigits = digits.len() as i32;
    if decpt <= -4 || decpt > 16 {
        // Exponent notation: d[.ddd]e(+|-)XX
        let mut chars = digits.chars();
        if let Some(first) = chars.next() {
            out.push(first);
        }
        let rest: String = chars.collect();
        if !rest.is_empty() {
            out.push('.');
            out.push_str(&rest);
        }
        let exp = decpt - 1;
        out.push('e');
        out.push(if exp < 0 { '-' } else { '+' });
        out.push_str(&format!("{:02}", exp.unsigned_abs()));
    } else if decpt <= 0 {
        out.push_str("0.");
        for _ in 0..(-decpt) {
            out.push('0');
        }
        out.push_str(&digits);
    } else if decpt >= ndigits {
        out.push_str(&digits);
        for _ in 0..(decpt - ndigits) {
            out.push('0');
        }
        out.push_str(".0");
    } else {
        let split = decpt as usize;
        out.push_str(digits.get(..split).unwrap_or(""));
        out.push('.');
        out.push_str(digits.get(split..).unwrap_or(""));
    }
    out
}

/// The text Python's `json.dumps` writes for a float with `allow_nan=True`: `repr` for a
/// finite value, and `NaN`, `Infinity` or `-Infinity` for the others.
///
/// ```
/// use console_pyjson::float_repr::json_float;
/// assert_eq!(json_float(1e22), "1e+22");
/// assert_eq!(json_float(f64::NEG_INFINITY), "-Infinity");
/// ```
pub fn json_float(x: f64) -> String {
    if x.is_nan() {
        String::from("NaN")
    } else if x.is_infinite() {
        String::from(if x > 0.0 { "Infinity" } else { "-Infinity" })
    } else {
        repr_f64(x)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // Expected strings recorded from CPython 3.14.7 `repr(float)`, run as
    // `python3 -I -c 'print(repr(x))'` with the standard library only.
    #[test]
    fn repr_layout_boundaries() {
        let table: &[(f64, &str)] = &[
            (0.0, "0.0"),
            (-0.0, "-0.0"),
            (1.0, "1.0"),
            (0.1, "0.1"),
            (0.0001, "0.0001"),
            (0.00001, "1e-05"),
            (0.00012345, "0.00012345"),
            (0.000012345, "1.2345e-05"),
            (9999999999999998.0, "9999999999999998.0"),
            (1e16, "1e+16"),
            (1.5e16, "1.5e+16"),
            (123456789.0, "123456789.0"),
            (1e15, "1000000000000000.0"),
            (5e-324, "5e-324"),
            (f64::MAX, "1.7976931348623157e+308"),
            (f64::MIN_POSITIVE, "2.2250738585072014e-308"),
            (0.1 + 0.2, "0.30000000000000004"),
            (1e100, "1e+100"),
            (-1.5e-7, "-1.5e-07"),
            (f64::INFINITY, "inf"),
            (f64::NEG_INFINITY, "-inf"),
            (f64::NAN, "nan"),
        ];
        for (value, expected) in table {
            assert_eq!(repr_f64(*value), *expected, "repr of {value:e}");
        }
    }

    #[test]
    fn exact_ties_round_half_to_even_as_cpython() {
        // Values exactly halfway between two shortest candidates (recorded from CPython
        // 3.14.7): CPython keeps the even last digit.
        let table: &[(u64, &str)] = &[
            (0x4318_01ea_5489_04e9, "1689376348324154.2"),
            (0x4309_8df8_d00e_09e2, "899121774969148.2"),
            (0xc310_308e_1773_cbad, "-1139246616081131.2"),
            (0x4302_03dc_ade6_71d2, "633849490755130.2"),
        ];
        for (bits, expected) in table {
            assert_eq!(repr_f64(f64::from_bits(*bits)), *expected, "bits {bits:#x}");
        }
    }

    #[test]
    fn json_float_writes_non_finite_names() {
        assert_eq!(json_float(f64::NAN), "NaN");
        assert_eq!(json_float(f64::INFINITY), "Infinity");
        assert_eq!(json_float(f64::NEG_INFINITY), "-Infinity");
        assert_eq!(json_float(2.5), "2.5");
    }
}
