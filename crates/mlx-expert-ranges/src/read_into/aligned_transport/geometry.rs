use super::*;

type Check<T> = std::result::Result<T, &'static str>;

pub(super) fn alignment(a: u64) -> Check<u64> {
    match a {
        4096 | 16384 => Ok(a),
        _ => Err("alignment"),
    }
}

/// Caller validates the public alignment. Small powers of two exercise this kernel in tests.
pub(super) fn geometry(a: u64, file: u64, offset: u64, len: u64, native: u64) -> Check<Window> {
    debug_assert!(a.is_power_of_two());
    if len == 0 {
        return Err("empty");
    }
    let end = offset.checked_add(len).ok_or("end-overflow")?;
    if end > file {
        return Err("out-of-file");
    }
    let mask = a - 1;
    let start = offset & !mask;
    let upper = end
        .checked_add((a - (end & mask)) & mask)
        .ok_or("round-overflow")?;
    let (kind, begin, bytes, delta) = if upper > file {
        (Kind::Edge, offset, len, 0)
    } else {
        (Kind::Window, start, upper - start, offset - start)
    };
    if bytes > native {
        return Err("native-size");
    }
    Ok(Window {
        kind,
        begin,
        bytes,
        delta,
        logical_begin: offset,
        logical_bytes: len,
    })
}

pub(super) fn backing(a: u64, largest: u64, selected: u64, native: u64) -> Check<u64> {
    alignment(a)?;
    if !(1..=MAX_SELECTED_BYTES).contains(&selected) {
        return Err("selected-limit");
    }
    let bytes = largest.checked_add(a - 1).ok_or("backing-overflow")?;
    if bytes > MAX_BACKING {
        return Err("backing-limit");
    }
    if bytes > native {
        return Err("native-size");
    }
    Ok(bytes)
}

pub(super) fn reservation(backing: u64, required_control: u64, budget: u64) -> Check<u64> {
    if required_control > CONTROL {
        return Err("control-limit");
    }
    if backing > MAX_BACKING {
        return Err("backing-limit");
    }
    let total = backing.checked_add(CONTROL).ok_or("budget-overflow")?;
    if total > budget {
        return Err("budget");
    }
    Ok(total)
}
