//! Pre-payload census of the Darwin loader, shared by the admitted child and its control.
use mlx_native_affine::fixture::sha256_hex;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::ffi::{c_void, CStr};
use std::fs::{File, Metadata, OpenOptions};
use std::io::{Read, Take};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};

const MAX_IMAGE_BYTES: u64 = 64 << 20;
extern "C" {
    fn _dyld_get_shared_cache_range(length: *mut usize) -> *const c_void;
    fn _dyld_get_shared_cache_uuid(uuid: *mut u8) -> bool;
}

fn stamp(m: &Metadata) -> (u64, u64, u64, i64, i64) {
    (m.dev(), m.ino(), m.len(), m.ctime(), m.ctime_nsec())
}

fn image_hash(path: &Path) -> Result<String, String> {
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)
        .map_err(|e| e.to_string())?;
    let original = file.metadata().map_err(|e| e.to_string())?;
    if !original.is_file() || original.len() == 0 || original.len() > MAX_IMAGE_BYTES {
        return Err(format!("invalid loaded image file {}", path.display()));
    }
    let mut data = Vec::with_capacity(original.len() as usize);
    let mut bounded: Take<&File> = (&file).take(original.len() + 1);
    bounded.read_to_end(&mut data).map_err(|e| e.to_string())?;
    if data.len() as u64 != original.len()
        || stamp(&file.metadata().map_err(|e| e.to_string())?) != stamp(&original)
        || stamp(&path.symlink_metadata().map_err(|e| e.to_string())?) != stamp(&original)
    {
        return Err(format!("loaded image file changed {}", path.display()));
    }
    Ok(sha256_hex(&data))
}

pub fn census(policy: &Value) -> Result<Value, String> {
    let hashes = policy["noncache_images"]
        .as_object()
        .ok_or("missing noncache image policy")?;
    if hashes.len() != 4 {
        return Err("expected original binary and three installed libraries".into());
    }
    let program = std::env::current_exe()
        .and_then(|p| p.canonicalize())
        .map_err(|e| e.to_string())?;
    if Some(program.as_path()) != policy["program"].as_str().map(Path::new) {
        return Err("native executable path mismatch".into());
    }
    let mut cache_len = 0;
    let start = unsafe { _dyld_get_shared_cache_range(&mut cache_len) } as usize;
    let end = start
        .checked_add(cache_len)
        .ok_or("shared cache range overflow")?;
    let mut uuid = [0u8; 16];
    if start == 0
        || cache_len == 0
        || cache_len >= 64usize << 30
        || !unsafe { _dyld_get_shared_cache_uuid(uuid.as_mut_ptr()) }
    {
        return Err("missing Darwin shared cache identity".into());
    }
    let uuid: String = uuid.iter().map(|b| format!("{b:02x}")).collect();
    if policy["platform_cache_uuid"].as_str() != Some(uuid.as_str()) {
        return Err("Darwin shared cache UUID mismatch".into());
    }

    let count = unsafe { libc::_dyld_image_count() };
    if count == 0 || count >= 4096 {
        return Err("invalid dyld image count".into());
    }
    let mut shared = Vec::new();
    let mut noncache = BTreeMap::<PathBuf, String>::new();
    for i in 0..count {
        let address = unsafe { libc::_dyld_get_image_header(i) } as usize;
        let name = unsafe { libc::_dyld_get_image_name(i) };
        if address == 0 || name.is_null() {
            return Err("missing dyld image header or name".into());
        }
        let name = unsafe { CStr::from_ptr(name) }
            .to_str()
            .map_err(|e| e.to_string())?;
        if (start..end).contains(&address) {
            shared.push(name.to_owned());
        } else {
            let path = Path::new(name).canonicalize().map_err(|e| e.to_string())?;
            let key = path.to_str().ok_or("native image path encoding")?;
            let expected = hashes
                .get(key)
                .and_then(Value::as_str)
                .ok_or_else(|| format!("unapproved non-cache image {key}"))?;
            let digest = image_hash(&path)?;
            if expected != digest || noncache.insert(path.clone(), digest).is_some() {
                return Err(format!("changed or duplicate non-cache image {key}"));
            }
        }
    }
    if unsafe { libc::_dyld_image_count() } != count
        || shared.is_empty()
        || noncache.len() != hashes.len()
        || !noncache.contains_key(&program)
    {
        return Err("unstable or incomplete native image census".into());
    }
    shared.sort();
    Ok(
        json!({"schema":"studio017-native-images/1","shared_cache_uuid":uuid,
        "shared_cache_bytes":cache_len,"shared_cache_images":shared,"noncache_images":noncache}),
    )
}
