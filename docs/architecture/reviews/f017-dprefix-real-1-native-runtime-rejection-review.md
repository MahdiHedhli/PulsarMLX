# F017 DPREFIX-REAL-1 Native-Runtime Rejection Review

`DPREFIX-REAL-1` crossed its reviewed consumption boundary exactly once. The
durable journal records 40 issued and 40 completed positional reads totaling
`1,431,263,232` packed bytes. The real-payload ledger therefore advances from
59 to 99 irrespective of the later numerical outcome.

The Q4_K and Q6_K hard identity gates passed. Their actual packed hashes are
present in the durable journal and material manifest. Their decoded identities
are established by the bound material-builder control flow: it raises the
named identity-confirmation terminal before descriptor creation on any packed
or decoded mismatch, while the complete 40-entry material manifest exists.

After the independent oracle values were constructed, the exact reviewed
candidate was launched and exited nonzero with `native candidate matvec
shape`. The terminal disposition is therefore `REJECTED / NATIVE_RUNTIME /
NATIVE_CANDIDATE_MATVEC_SHAPE`.

No candidate evidence artifact was created. Consequently no completed repeat,
paired Tier-B row, dispatch record, lifecycle reconciliation, or retained
layer-2/layer-3 package exists. The material builder also computed but did not
persist the 38 first-observation decoded hashes. Those unavailable fields were
not recreated: there was no checkpoint reread, candidate recomputation, oracle
recomputation, or retry.

Raw terminal evidence:
`docs/architecture/reviews/evidence/f017-dense-prefix-real-attempt-1-rejected-native-runtime-v1.json`
with SHA-256
`a21af1ed489382bfed211682f4cc471744235d13acd97e8a4866089532eaef34`.

Representative M1-F0 remains not authorized and not executed. The exact next
action is independent adversarial review of this failure evidence; the consumed
attempt may not be retried.

Final Apple-native CI run `31971520387` passed both required jobs at exact head
`6bcc721885b33df1fe3b4ca274ec58c2b42cd72c`. That head is the immutable real
evidence commit `594021194c8e70d92965e344780879ed53003f84` plus a checkpoint-free
workflow correction that replaced its stale pre-event ledger assertion with
the banked terminal state. No real computation or access was repeated.
