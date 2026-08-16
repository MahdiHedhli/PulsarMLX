# PulsarMLX F017 DPREFIX Real-Event Orchestrator Closure Report

- Starting SHA: `9ff5e8fef912972a0521932fbc3ec54660d70cf1`
- Prior stop evidence SHA: `54eb2ef149d9cbd8c2e1159477ddab7ed1fec5780531fee59d46df1faac891bc`
- Attempt: `DPREFIX-REAL-1`; `SAME UNCONSUMED DPREFIX ATTEMPT MAY CONTINUE`
- Current ledger: `59`; checkpoint access: `0`
- Orchestrator source manifest: `6444db4def93cee97d82fd04ed41eb3ce2a3ec60c4a7f780b0a4bd46e41d5afe`
- Orchestrator package: `4b69d8fcca3edf6edbe78e75d62d5b9558d58ac90f7d70fbae79484e017f18df`
- Bounded reader: `c0ebeed0adb97f077465bba8af8c76e841d521fa16ee630a49cddd21025448d1`
- Material builder: `2576a4d8d09687200e710e45ee16c2e2a086bed80520bb68ce285315f2d9fbff`
- Decoder dispatch: `8b5d12621964c9197a5eab012e8097a5b36ba21549728f8653092f5be51c4fee`
- Journal/ledger writer: `24f5db33773686bcb8d22c16136e3a9f3e6e37d173c46d2e9a3bc9c146171a5d`
- Oracle-first coordinator: `217521280217f9c28944a537249f6b91395cd1b71ecf9253fae4a656ac021f3d`
- Candidate launcher/IPC: `cba54f38902bfd964fe675f9ed1332bed06fc1eef3076141200d2e01fac11db4`
- Metric coordinator: `2cf37ea4a58da2da3701d10cb72e938747feb68a70c19097ff0d54c50b619114`
- Retention builder: `9c2cd3913248557a41cda0bcec75fc98e6b7fd044c4f72b843e7d00b6d2253ba`
- Terminal evidence banker: `86a4f08d821a41ce5afb7c84607da82a340bae508a79f38d2cd4ceb615d0aef6`
- IPC schemas: `fd3b6247ea2fa9312659f5b279e70d575f88a3e74f22b86b330ea94da5ff2342`
- Config v5: `27774a11d933750cb9703a9889b5f83b88711ee27827c9d34eb585649545aadd`
- Authorization v4: `fc286651d4fa11ff43e0db926a801d24e30152509465d2d7f0510d79599e1e47`
- Attempt ledger v6: `09478ffdf4180655006cc4ce9d634c62af020f2a7fb3c4ce02f3220f509ba948`
- Preflight: `READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE`
- Rehearsal: `FULL_REAL_EVENT_ORCHESTRATION_INSTANTIABLE_CHECKPOINT_FREE`
- Partial-failure campaign: `0d786734e4ffca2402830afd4bb457fc915ec097b43ed0bf6c83726a0573a50c` / `PASS`
- Q4/Q6 mismatch campaign: `c779fb0de372b3290bc93a5664ccf3018109deda37bde8c2305453d92e44a767` / `PASS`
- Extra-read attacks: `29e12447be857c0a47c832d74b6eb8fd13381ca4675e90a574d7891d7e8e8ca4` / `PASS`
- Memory floor: `27 GiB` remains the non-consuming minimum; compact journal/package overhead is bounded below the existing reserve
- Internal verdict: `GO FOR DPREFIX REAL-EVENT ORCHESTRATOR ADVERSARIAL REVIEW`
- Final CI: pending final-head Apple-native binding

Exact next action: independent adversarial review. No checkpoint access before a `GO FOR ONE DENSE-PREFIX M1-F(-1) REAL CAPTURE` verdict.
