# Allowed validation

Use PYTHONDONTWRITEBYTECODE=1 and PYTHONPATH=scripts/research.
Run python3 -m unittest discover -s scripts/research/tests -p test_f020_staged_v4.py.
Select retained CPU tests after auditing imports/commands; do not run native
qualifiers or a blanket workspace test that initializes MLX. Offline Python bytecode compilation
to own audit only; record exact commands/build flags/artifact hashes in own attempt.
Independent review must ACCEPT/0 both design and final exact package. No capability
issuer is called. Native-only checks explicitly NOT RUN. No real data path is used.

Retained safe candidates: test_f020_selected_v2.py (fixtures/proof/r1 and inherited
stdlib exp), test_f020_selected_authority_v2.py (synthetic JSON parser), synthetic
snapshot decode_header controls from test_f020_selected_snapshot_v2.py, and mocked
report gates from test_f020_selected_gates_v2.py after checking their test bodies.
Ledger issuance tests are not run in this scope. All imports are source-inspected
for no MLX initialization. Process tests require separate owned-child inspection.
Normalize measured ru_maxrss Darwin bytes/LinuxKiB before cap comparison.

No Cargo step for this Python-only additive scope. Full positives use fresh CPU
subprocesses with absolute lifetime RSS caps; no baseline-relative acceptance.
