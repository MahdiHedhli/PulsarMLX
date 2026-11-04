//! Host-only policy selection shared by the real parent and regression tests.
use serde_json::{json, Value};
pub const SCHEMA: &str = "pulsarmlx.m1a-continuation/1";
pub fn raw_allowed(f: &Value, phase: Option<&str>) -> Result<Option<bool>, &'static str> {
    match f["schema"].as_str() {
        Some("pulsarmlx.adoption-host-freeze/1") => Ok(None),
        Some(SCHEMA) => {
            if phase != Some("m1a") || f["phase"] != "m1a" {
                return Err("continuation is m1a only");
            }
            let allowed = match (f["host_role"].as_str(), f["raw_policy"].as_str()) {
                (Some("native-ci"), Some("CI_FRESH_ONCE")) => true,
                (Some("m1-ultra-studio"), Some("STUDIO_RETAINED_OBSERVATION")) => false,
                _ => return Err("closed host/raw policy pair required"),
            };
            if f["raw_probe_budget"] != json!({"allowed":1,"used":u8::from(!allowed)})
                || f["raw_execution_authorized"] != json!(allowed)
                || f["raw_provenance"]["applies_to_current_binary"] != json!(allowed)
                || f["M1b_released"] != false
                || f["shipping_default"] != "copied"
            {
                return Err("raw ledger/provenance/scope mismatch");
            }
            Ok(Some(allowed))
        }
        _ => Err("unknown freeze schema"),
    }
}
