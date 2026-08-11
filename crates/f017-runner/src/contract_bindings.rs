use crate::json::sha256_bytes;
use std::collections::BTreeMap;

pub const R12_CONTRACT_VERSIONS: [&str; 4] = [
    "f017-production-expert-tier-b-v1",
    "f017-production-r9-tier-b-v2",
    "f017-production-r10-tier-b-v2",
    "f017-production-r11-tier-b-v1",
];

pub fn r12_contract_bindings() -> BTreeMap<String, String> {
    [
        (R12_CONTRACT_VERSIONS[0], include_bytes!("../../../specs/017-rust-native-inference-runtime/contracts/production-expert-tier-b-v1.json").as_slice()),
        (R12_CONTRACT_VERSIONS[1], include_bytes!("../../../specs/017-rust-native-inference-runtime/contracts/production-r9-tier-b-v2.json").as_slice()),
        (R12_CONTRACT_VERSIONS[2], include_bytes!("../../../specs/017-rust-native-inference-runtime/contracts/production-r10-tier-b-v2.json").as_slice()),
        (R12_CONTRACT_VERSIONS[3], include_bytes!("../../../specs/017-rust-native-inference-runtime/contracts/production-r11-tier-b-v1.json").as_slice()),
    ]
    .into_iter()
    .map(|(version, bytes)| (version.to_owned(), sha256_bytes(bytes)))
    .collect()
}
