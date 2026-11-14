//! Candidate-bound startup verifier and compiled source closure.
pub const SEAL: &str = "staged-weighted-native-build-v1.dcf6bc045c5a024b269d2c5421d2277596ad83e7267d2713389058ac8403f575";
pub const REFERENCE: &str = "6ab6d2d0cc17f95eb18f25ed6230b4e281df7026b446845c60788892e87b587e";
pub const MODULES: &[(&str, &str)] = &[
    ("f020_expert_mlp_r1_v1", "3aad179cda4d4fe054d4a4b52fd3ef4911956559ac2cdad131b435bb03d81f01"),
    ("f020_expert_mlp_qualify_v1", "366762e6cd85b8fa28495950a20031378ca1084351e4e2bc88cdb7aa39dcf6af"),
    ("f020_resident_mlp_fixtures", "9945784b1a205fec611e316d8f74c5ccd760361704ac9a0bf66e7c7de8388702"),
    ("f020_resident_mlp_runtime", "3dbffb97f61665a7152764b3481d5077aaf2e4ca635f1b10e468ff18f712213a"),
    ("f020_resident_mlp_check", "006a4440e1028b9d85ede45fd9a9f16abd474a51e6ce6ebe47f068174c0d0530"),
    ("f020_resident_mlp_supervise", "4816ac694c21b1a07e5cd8f47f18476942fb4aa7ab1005c01e161f41cf8e22b1"),
    ("f020_weighted_mlp_reference", "34716ebc94b441d2e2d4f44068da1ff54de6ce34a773f166109189a81333d26e"),
    ("f020_weighted_native_rational", "021d270c11bae21d5f6def619665afdbf74f86875fc9303e1fbb819946dbe705"),
    ("f020_weighted_native_reference", "d1c1d8b7b90c66bd77be8604621d84525529bb1326b49f31b3ea57c5b1311156"),
    ("f020_weighted_native_check", "74aa70317d6040838834a4a9953353553e56167b388d183be53322be305c1789"),
    ("f020_admission_screen_reference_v1", "a42c4131056c3db8aec64bcda98d30ba678d7db8b9fcfa5f14cb523d8a62f055"),
    ("f020_staged_weighted_check", "7746324c77b490e7c4e630f667d7d9461d9d23208d2ac6154ab554f100ddd962"),
    ("f020_staged_weighted_bootstrap", "38a3bcf6c337528e7f5621ffcf3d78fa76e6e58a7a999719e524b93a365b02e6"),
    ("f020_staged_weighted_supervise", "8ca180966fd78ef8849183dcbd2964b1ae153a6031bc3f95b0b5beb1c4f7439b"),
];
