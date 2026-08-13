# F017 M1-F Internal Implementation Review

## Verdict

`NO-GO`

The accepted M1-E state and layer-3 catalog metadata are internally
consistent. The complete layer would require six attention matvecs, one router
matvec, twenty-four routed-expert matvecs, and three shared-expert matvecs per
repeat. The historical layer-3 route also contains accepted M1-E expert 15.

The admission package cannot yet bind a truthful exact expert tensor allowlist.
The requested new independent hidden state has never been evaluated through
the real layer-3 attention/router. The only banked top-8 is tied to the distinct
checkpoint-derived `token_embedding[9703]` input. Treating those expert IDs as
valid for new bytes is a composition defect; authorizing all expert slices is
an isolation defect.

No runtime or numerical implementation change can establish the missing route
from metadata. A separately scoped oracle-admission decision is required.
Until then there is intentionally no M1-F execution config, preflight PASS,
adversarial packet, or authorization.
