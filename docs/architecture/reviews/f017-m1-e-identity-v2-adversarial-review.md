# F017 M1-E Identity v2 Independent Adversarial Review

## False-pass attempts

- correct checkout with stale binary: rejected by embedded-runtime and
  executable SHA-256 checks;
- correct binary with wrong checkout: rejected by exact authorization head;
- descendant with hidden runtime or decoder drift: rejected by the
  deterministic category allowlist;
- authorization cherry-picked onto unrelated history: rejected by ancestry;
- matching artifact files on an unrelated branch: rejected by exact head and
  ancestry before content is used;
- correct ancestry with execution-config mutation: rejected by config SHA;
- stale runtime SHA in authorization: rejected by embedded identity;
- runtime built before decoder-v2 correction: rejected by runtime/executable
  identity and decoder artifact hash;
- dirty execution-controlled file: rejected by clean-tree gate;
- same path with changed content: rejected by direct SHA-256.

## Conclusion

The model no longer conflates executable identity with repository state, and
it does not weaken trust to ancestry alone. The authorization checkout is
exact, the permitted delta is classified and hash-bound, executable identity
is independent, and all load-bearing content remains directly hashed.
Attempt 2 remains unexecuted and unconsumed.

## Verdict

GO FOR M1-E ATTEMPT 2
