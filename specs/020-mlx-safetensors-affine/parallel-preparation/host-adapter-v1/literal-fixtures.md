# Independent authored literals frozen before implementation

These are expected DESIGN outcomes, not observations. MIT; authored for PulsarMLX.
Canonical descriptor=('toy-checkpoint','graph-v1','recipe-v1'), request='A', origin13,
capacity8, epoch0/revision0. Trunk bytes are ASCII `0123456789abcdef` exactly16.
KDA raw=(0,0,0,0,0,0,0), a=(0.25,-0.5), beta=0.75. Suffix both rows allzero.
Recurrent=((1,-2,3),(0.5,1.5,-0.25)). Output exactly(0,0,0); suffix remainszero;
new recurrent row i is initial row i times exp(-5/(1+exp(-exp(.125)*(a[i]+bias[i])))), bias=(.0625,-.125).
Sparse token=((.25,-.5),(.75,-1),(.5,.25),1,(.25,.5,-.75),(1,-.5,.25),(1,-2,3)).
Literal output=(1,-2,3), selected=(13,), history=(13,(.25,-.5),(.75,-1),(1,-.5,.25),(1,-2,3)); query and weight are NOT persistent history.
The nonzero-mixed second fixture replaces KDA raw with(.125,-.25,.375,-.5,.625,-.75,.875); independent retained chronological oracle computes expectations without importing state/candidate helpers. New oracle may import the independent frozen oracle only, never candidate/adapter helpers. Zero-output analytic first fixture does not substitute for the nonzero case.

Literal binary64 little-endian words (hex) used to build payloads without struct.pack:
0:0000000000000000, -0:0000000000000080, .125:000000000000c03f,
.25:000000000000d03f, -.25:000000000000d0bf, .375:000000000000d83f,
.5:000000000000e03f, -.5:000000000000e0bf, .625:000000000000e43f,
.75:000000000000e83f, -.75:000000000000e8bf, .875:000000000000ec3f,
1:000000000000f03f, -1:000000000000f0bf, -2:00000000000000c0, 3:0000000000000840.
K payload is7 zero words then(.25,-.5,.75); S payload is flattened sparse partitions above. Opposite-endian bytes3ff0000000000000 independently decode as positive subnormal integer61503*2**-1074; valid content is accepted as that value, never interpreted as1. Reject 000000000000f87f NaN,000000000000f07f Inf,0000000000002240=9. Decode oracle extracts sign/exponent/fraction via int.from_bytes, not implementation struct calls. Partition oracle is authored tuple values above.

## Additional success populations

Three-layer sorted(0,3,4), one token, independent instance: K80/S128/K80/T16;
limits=(16,288,0,32,304,0),total640,slots4. Allzero baseline.
Reserve ledgers: (0,80,0,8,80,0);(0,208,0,16,208,0);(0,288,0,24,288,0);(16,288,0,32,304,0).
After all reads unchanged. Admit ledgers: (16,288,0,32,224,0);(16,288,0,32,96,0);(16,288,0,32,16,0);(16,288,0,32,0,0).
Ack ledgers scratch24,16,8,0 with trunk16/experts288 unchanged; expert eviction reduces experts208,80,0. Terminal(16,0,0,0,0,0),slots1,generations(1,1,1,1). Layer0/4 analytic K outputs0 and same recurrence; sparse output above. Context becomes epoch0/revision1/position14.

Count8 at origin13, layers(0,3), independent instance: repeat each literal token8 times, K640/S1024/T16; limits=(16,1664,0,24,1680,0),total3384,slots4.
Reserve: (0,640,0,8,640,0);(0,1664,0,16,1664,0);(16,1664,0,24,1680,0).
Admit: io1040,16,0; ack:scratch16,8,0; evictK experts1024 then evictS0. TerminalT16slot1 gens1110. Position21/revision1; sparse values always(1,-2,3); selections per token at origin13: (13),(13,14),(13,14,15),(13,14),(13,14,17),(13,14),(13,14,19),(13,14), because equal full-pool scores choose pool0 and incomplete tail remains. KDA recurrence rows initial*decay**8; all outputs0. Same adapter count1 at21 refuses Step after ack due exhaustion; never a second execution. A fresh context with position21 can only be constructed as a test seam; no silently extended context creation.

## Cancellation/reset literal population (canonical K80/S128/T16)

Coordinates before=(epoch0,revision0,origin13,position13,capacity8,endpoint21).
Cancel preserves these coordinates in every uncommitted phase. Reset changes them to(1,1,20,20,8,28); B's separate context unchanged. Both invalidate old intent.

Reserved-all / pendingread-K / all-readcomplete: initial ledger(16,208,0,24,224,0),slots3,gens1110. CancelK quiescent gives(16,128,0,16,144,0); cancelS gives(16,0,0,8,16,0); cancelT giveszero. If K pending, its refund is delayed: cancelK unchanged; cancelS=(16,80,0,16,96,0); cancelT=(0,80,0,8,80,0); real readK cancellation completion thenzero. Release/evict leaveszero slots0,gens1110. Reset uses these same resource traces and changed coordinates above.

Published-ready / captured / pinned: initial(16,208,0,24,0,0),slots3. Without pins cancelK=(16,128,0,16,0,0); cancelS=(16,0,0,8,0,0). With pins cancelK=(16,208,0,16,0,0),cancelS=(16,208,0,8,0,0); K unpin drops80 then S unpin drops128. T nevercancelled; unpin if needed/release refunds finalscratch8. TerminalT16slot1/gens1110. Dispatch count0; reset stale intent must not dispatch.

Dispatched-all / proposal-computed: initial(16,208,0,24,0,0),slots3,pinsall. Cancel marksK/S; no ledger change; T notcancelled. Actual ackK(cancelled)=(16,208,0,16,0,0); ackS(cancelled)=(16,208,0,8,0,0); ackT(completed)=(16,208,0,0,0,0). UnpinK thenS drops experts128 then0; release/evict experts and releaseT terminalT16slot1,g1110. Proposal discarded, no commit. Reset changes coordinates before cleanup and retains identical quiescence accounting.

Partial completion K already completed: start(16,208,0,16,0,0),pinsall. CancelK is quiescent but pin holds80, cancelS pending holds128, T pending normal. AckS(cancelled)=(16,208,0,8,0,0); ackT(completed)=(16,208,0,0,0,0); unpin/drop K thenS givesT16,slots1,g1110. No commit. Already completedK must never be re-acknowledged.

Output-occupied: state=(0,1,13,14,8,21),storageT16slot1,g1110,A=(16384,32768,0,0). reset20 refuses Busy and leaves ALL unchanged. Redelivery unchanged. Ack/abandon =>A=(16384,0,0,0),same state; reset20 then gives(1,2,20,20,8,28),T16stillcharged. Next storage step Used; no trunk teardown/reuse.

All aborts after true quiescence restore adapterA=(16384,0,0,0); explicit pending cancel still holds pre-reserveA=(65536,32768,8192,8192). Completed success+retentionA=(16384,32768,0,0). Every reset-with-active phase above is tested independently on a fresh instance, never sequential steps.

Constitution-compliance check: prospective literal independently authored synthetic expectations satisfy principles I/III/XI and Governance lines166–168; tests must still demonstrate them before observed success is claimed.

Nonzero KDA independent oracle call is exactly:
`oracle.kda((token,), kernel, initial)` where token=(raw,(.25,-.5),.75), raw=(.125,-.25,.375,-.5,.625,-.75,.875), initial=(((1.,-2.,3.),(.5,1.5,-.25)),((0.,)*7,(0.,)*7)), and independently specified kernel=tuple(((c+1)/32,-(c+2)/64,(c+3)/32) for c in range(7)). These are frozen toy taps, not imported fixtures.kernels or implementation helpers. Compare outputs, recurrent matrix and suffix with the stated new tolerance. All literal sources use explicit chunk5/empty actions except the named read-failure substitutions in interface-v1.
