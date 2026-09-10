# Active-source CI input provenance closure

The primary confined CI consumer hashes all 38 rows in
`scripts/ci/f017_primary_ci_inputs_v1.json` from the active checkout. It raises
`CURRENT_ACTIVE_SOURCE_DRIFT:<repository_path>` when any current body differs
from its manifest digest. The frozen measurement is a separate input: version 8
remains bound to commit `f35d341110c67377200ad353ab56a3cf38615a73`, record
digest `c529221a53a338dfe57d65f855f1b9d9b11e0b0251562f84067a65a0538a6414`,
and 36 historical Git objects.

The preceding repair updated the secondary-wrapper row from the exact body at
`5b39a21aa8369ea2e53ea8e406002cc74250cec3` to the reviewed active body at
`e7759c3e7be0edf8098e3c9e29c37db88e694e7f`. Exact-head CI run `34485355258`
then advanced past that wrapper and exposed the only remaining mismatch: the
validator row still named digest `5a123ec88b805df77d00be1f42a6e6f13dcb7c6c69b06f09deb102761872628c`.
That digest is the exact validator body at `5b39a21aa8369ea2e53ea8e406002cc74250cec3`.
The validator was subsequently hardened at `0ae4c6f13fb8a103d1cee7ee3d070db4477dbb94`
and reached its reviewed current body at `f52cd00659a76c9a39d240451743d5b0175bc819`,
digest `dec34ba2157f04dcea6e64347bb96dc4288bfc8d676fdb1b10801c5146602253`.
This change updates only that stale digest.

## Complete active inventory

Every digest below is the SHA-256 of the named file in the candidate checkout.
“Active/legacy” identifies deliberately retained V2 numerical or V10 target
source content that is still consumed from the active checkout. “Match” means
the row needed no change.

| # | Repository path | Bytes | Current SHA-256 | Latest authorizing commit | Role | Disposition |
| ---: | --- | ---: | --- | --- | --- | --- |
| 1 | `docs/architecture/reviews/evidence/f017-v11-full-geometry-qualification-v2.json` | 886 | `860493afff3069a6e837aed45a70f363cc0a85c1ae1da5fe6b1df127f6aaf696` | `5528ae22d2bf9f9b086a1201c54cba9f05b3a2ee` | Active | Match |
| 2 | `scripts/research/tests/f017_sequence54/observation_oracle54.py` | 11226 | `f3190ada6ab51a735bf4d97c5a7a0a1feb75ccedfaa46c086ba473dafdcb40ba` | `6f59d9db93e92afed142b543a0e2fc19e0362bb4` | Active | Match |
| 3 | `scripts/research/tests/f017_sequence54/primary_faults54.py` | 16435 | `6d16ce257ae60a7b2207774ad7c10ebb4def74384b93da01bd8a885db326a72c` | `6f59d9db93e92afed142b543a0e2fc19e0362bb4` | Active | Match |
| 4 | `scripts/research/tests/f017_sequence54/primary_suite54.py` | 17908 | `cdadf472d197aff23d55e9cb678fff65180201e59ebd3476c72896344db967a3` | `1f49d767de96a6cc716fa074580dc2ac73733e3d` | Active | Match |
| 5 | `scripts/research/execute_f017_corrected_oracle_event_v11.py` | 14073 | `967c1d5566e9faae801d1641c9839497d9ecc79aae28b34f1d6dba6679aba1fe` | `53c114f72eb6046bd60c2de74c2762374ea72bfa` | Active | Match |
| 6 | `scripts/research/f017_accounting_root_continuity_v1.py` | 19803 | `57d407d827c27a5228916805b437e8d2386cd596c271d3e941f64d9f512e9ab7` | `456b5d8d32bab01fb00fb98c25b1261be42e94e7` | Active | Match |
| 7 | `scripts/research/f017_binary_comparison_authority_v11.py` | 8361 | `10235d8482aa66a318d7e97b7d3b9fbf27859a732cf67bf29d9cbcd19596e352` | `8bc7c468d685cb446f8187324385104ee87d6bc2` | Active | Match |
| 8 | `scripts/research/f017_bounded_artifact_decode_v1.py` | 10549 | `60ad48f765b0a9924fb534204b6d85eecc975d6624110ca4f9a5133136f931fa` | `1ae7e8248088aeef0ce08e1f5c531e4ff1e20b25` | Active | Match |
| 9 | `scripts/research/f017_canonical_serialization_v10.py` | 1390 | `7faa1d292c61257024e8aa1e4b337f395cea4c3e4e2dafa476661aeb9dc3872d` | `11e4c7e911752214708fc8077c78a9345a7181ca` | Active | Match |
| 10 | `scripts/research/f017_corrected_oracle_primary_numerics_v2.py` | 14086 | `657cdff9ee833cb2b3a0b3fa71b6cbc3dd1e0fbc71b74b9bbff9dca6b5b76767` | `b69117800eb3123cc61ef7d2a5537cea750184a9` | Active/legacy | Match |
| 11 | `scripts/research/f017_corrected_oracle_primary_numerics_v3.py` | 18217 | `56f4179a58ff9558e143e79af73f9709e731ca74b6536f346b1a8e1b29e3f3a6` | `2e24307715a498d12249df71a036ba310f32255f` | Active | Match |
| 12 | `scripts/research/f017_corrected_oracle_primary_target_source_v10.py` | 7931 | `ceab082d593a22fc30f76e67947b1819809edf0be488476f7affa326f5e744f4` | `6f59d9db93e92afed142b543a0e2fc19e0362bb4` | Active/legacy | Match |
| 13 | `scripts/research/f017_corrected_oracle_primary_target_source_v11.py` | 1057 | `33e6473aff9ba468b0614d5f06261c8995bf4ac609f9b61e59c6238b9cd99f74` | `6f59d9db93e92afed142b543a0e2fc19e0362bb4` | Active | Match |
| 14 | `scripts/research/f017_corrected_oracle_primary_wrapper_v11.py` | 5113 | `515b23b0ac4fd382b9f4a75d01b4bbabe079020e17834347d6c1cfa2d7529133` | `1f49d767de96a6cc716fa074580dc2ac73733e3d` | Active | Match |
| 15 | `scripts/research/f017_corrected_oracle_secondary_numerics_v2.py` | 10073 | `e3670b22ac71bad7523efe1e47b00f2345d1f103d2af8f7592e2f3f8c793a791` | `b69117800eb3123cc61ef7d2a5537cea750184a9` | Active/legacy | Match |
| 16 | `scripts/research/f017_corrected_oracle_secondary_numerics_v3.py` | 14177 | `c1b6b95cf2a597453aeecc43bf1d5c6df5b8488a6ac522bd01771af7b4d0e7d3` | `2e24307715a498d12249df71a036ba310f32255f` | Active | Match |
| 17 | `scripts/research/f017_corrected_oracle_secondary_target_source_v10.py` | 7657 | `421e3c9c414257527cc20b43906326323bc22d8fc65be3e195048957f40a21b8` | `025433364b45c8749447271ff1f1806a4231ffeb` | Active/legacy | Match |
| 18 | `scripts/research/f017_corrected_oracle_secondary_wrapper_v11.py` | 6171 | `77b3b473f3744c88f37ab18175df6ace4f6e44d6b15aeefa1832aa3913834586` | `e7759c3e7be0edf8098e3c9e29c37db88e694e7f` | Active | Match after C |
| 19 | `scripts/research/f017_descriptor_lease_manager_v10.py` | 17814 | `9cf85bc57548a9d2fd176cb3d02acf2bc88aba5c136a2c747ac386c535003ae2` | `1ae7e8248088aeef0ce08e1f5c531e4ff1e20b25` | Active | Match |
| 20 | `scripts/research/f017_oracle_primary_decoders.py` | 8476 | `60a4b4e7d973edc41383e20d6d3413d4f658bf4a34dc9132529a6c702b44e11e` | `e00811df76c480b53b1bcab35fcb01ea8475b089` | Active | Match |
| 21 | `scripts/research/f017_primary_observed_descriptor_source_v1.py` | 8761 | `752fd55ba1ad641e3ab26b545e983a6bf798032d75a916e83e6c8fc2f701d28b` | `6f59d9db93e92afed142b543a0e2fc19e0362bb4` | Active | Match |
| 22 | `scripts/research/f017_primary_read_observation_v1.py` | 28825 | `16165f7dfb1060d72d79545e9986d439229b80691f4cc34ccebf66661724d5ec` | `6f59d9db93e92afed142b543a0e2fc19e0362bb4` | Active | Match |
| 23 | `scripts/research/f017_result_artifacts_v11.py` | 24390 | `d82af8629c8ad989baa760c13cea94a7e42bd3628aa6a5e24a6795dc33fa4ae4` | `8a40fbdc2d956b96eda332c0adce267ad4c588a5` | Active | Match |
| 24 | `scripts/research/f017_result_bundle_authority_v11.py` | 6225 | `f1388876fa24d4f93d6cd0732c6648584177b353c2bd1f37f6a02d3b3e948a3a` | `53c114f72eb6046bd60c2de74c2762374ea72bfa` | Active | Match |
| 25 | `scripts/research/f017_result_bundle_builder_v11.py` | 11577 | `8853623824f4546e419c1b51766cf1cb39f2b8a2b61e59e25f25dba89c01c70b` | `5b39a21aa8369ea2e53ea8e406002cc74250cec3` | Active | Match |
| 26 | `scripts/research/f017_result_envelope_v11.py` | 17986 | `572f4f03e8e02a8f9b13ef007b06e0e727089878d1187d81a4d70afb4c3870bf` | `5b39a21aa8369ea2e53ea8e406002cc74250cec3` | Active | Match |
| 27 | `scripts/research/f017_write_once_artifact_v1.py` | 3101 | `da1eeead2fceb475557456048bd8bda1f3bfdbde5c407d4ddc3c92b6ee83e768` | `5b39a21aa8369ea2e53ea8e406002cc74250cec3` | Active | Match |
| 28 | `scripts/research/generate_f017_corrected_oracle_fixtures.py` | 3495 | `c611e0b684b86ab6e8064b10fc9b5ef1aefa11af1dbc1006fe1163ce82107526` | `e00811df76c480b53b1bcab35fcb01ea8475b089` | Active | Match |
| 29 | `scripts/research/iq2_xxs_tables.py` | 5983 | `050b2ed26afbe6f15abf1dcd3789d6cddd93cee4ce87e8b13e86cf3f503aa756` | `910c69a9c2ee89837184fbf797ce27ea041706cd` | Active | Match |
| 30 | `scripts/research/iq3_xxs_tables.py` | 2833 | `87f01f518f954fa095b20e0ea8112a6073a4a88d394046c145052404437c5042` | `e9cffe22fc9d7d78806c08782d4ffb2cb3eeb6c2` | Active | Match |
| 31 | `scripts/research/iq_extra_tables.py` | 21693 | `08c0f3cf2fa33d7a51109959d773f2ae21f282c166b848d154903ce51f38d83e` | `83014ce72a15b21713c1a426989e28db7cbcd0eb` | Active | Match |
| 32 | `scripts/research/tests/f017_primary_integration_cases.py` | 8977 | `03ef0fcbe9a0687f1a9b5fd9407ab1ff5ef082e3128c5e3312488ecc7ff64711` | `6f59d9db93e92afed142b543a0e2fc19e0362bb4` | Active | Match |
| 33 | `scripts/research/validate_f017_v11_execution_authority_v1.py` | 21944 | `dec34ba2157f04dcea6e64347bb96dc4288bfc8d676fdb1b10801c5146602253` | `f52cd00659a76c9a39d240451743d5b0175bc819` | Active | Re-pin in D |
| 34 | `specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-geometry-v1.json` | 614 | `a9037a42a476092bdc0f870a7e0b6162a1df0abbe5b0663218e82f931676846a` | `0f0fc80876ba6f9e11615b3c8dd29c72b4b90451` | Active | Match |
| 35 | `specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json` | 13137 | `a555abe0ff2aff03a693ac7313d4af17061d01766e90971d92a7ba528f4995f2` | `2e24307715a498d12249df71a036ba310f32255f` | Active | Match |
| 36 | `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-active-generation-v11.json` | 327 | `755912461bd9818cfacb98bc03f325f7fbcea3cd034efc4951b5fdde40434447` | `53c114f72eb6046bd60c2de74c2762374ea72bfa` | Active | Match |
| 37 | `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-binary-result-envelope-v11-v2.json` | 3173 | `9f2812c70d248d15e0f39e14dc047d815c5c9c0a19257bd122fa64ade078ea67` | `53c114f72eb6046bd60c2de74c2762374ea72bfa` | Active | Match |
| 38 | `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-result-authority-v11-v2.json` | 2589 | `4fd71e90f4184e5f2c7449eac6089f7392f1cc0d1961aecb0243f7ef723af101` | `53c114f72eb6046bd60c2de74c2762374ea72bfa` | Active | Match |

## Verification boundary

The whole-inventory test extracts and executes the production consumer's exact
active-row loop across all 38 entries. It proves the corrected manifest passes
as one set and reproduces the stale validator failure. Mutation cases cover a
wrong digest and changed source bytes through the real loop. Schema, path, role,
historical substitution, missing-entry, and duplicate-entry cases are explicit
test-side guards; the test does not claim those guards exist in the consumer.

The same module verifies the frozen measurement record and all 36 historical
object digests with `git show` only. It never executes historical source or
opens checkpoint data. The 10 focused wrapper tests and their results belong to
the preceding C repair; D reports its new 11-test whole-inventory result
separately. The nested test module is a direct local check, while the unchanged
hosted workflow remains authoritative for the complete confined CI step.

This closure does not change workflows, the source base, role declarations,
historical records, runtime or numerical code, validators, wrappers, checkpoint
access, Event 06 state, or the retained SEC02–SEC05 findings. The existing
artifact ledger remains at 175. Hosted exact-head CI determines whether the
formerly failing full step passes and whether any later independent step fails.
