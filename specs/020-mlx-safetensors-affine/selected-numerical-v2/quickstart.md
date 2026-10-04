# Reproduction gates

Host-only commands:

```sh
python3 -m unittest discover -s scripts/research/tests -p 'test_f020_selected*v2.py'
python3 -O scripts/research/f020_selected_proof_v2.py
cargo test -p mlx-expert-mlp --test selected_snapshot --offline
```

Fixture generation requires an explicit private audit directory. No default
native execution command is enabled. The complete source/build capability
verifier and final independent ACCEPT/0 must exist before any numerical command.
The preliminary host-source review cannot substitute for that gate.
