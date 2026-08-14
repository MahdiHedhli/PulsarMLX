# F017 M1-F0 analytical recovery internal review

Verdict: `GO FOR ANALYTICAL-RECOVERY ADVERSARIAL REVIEW`

## Scope and result

This review covers only accepted-boundary evidence recovery, analytical-retention repair, route-stability evaluation, executed-validator amendment, and the mandatory stop. It does not authorize a new route, Q6_K qualification, expert execution, or M1-F.

The single recovery opened one accepted shard and performed exactly twelve positional payload reads (139,217,920 compressed bytes; 666,430,464 decoded bytes). It reproduced the accepted attention output, attention residual, router-normalized input, complete router-score vector, complete ranking, selected-ID bytes, routing-weight bytes, and selected IDs exactly. No expert payload or MLX candidate path was accessed.

## Findings

1. Recovery identity: PASS. All seven accepted identities and `[166, 78, 26, 186, 163, 199, 233, 177]` reproduced exactly.
2. Analytical retention: PASS. Complete probability, bias, score, score-bound, ranking, selected-ID, and routing-weight values now have canonical typed-byte identities and machine-readable values.
3. Contract ordering: PASS. `m > B8 + B9` and minimum safety factor `4.0` were frozen before rank-8/rank-9 values were inspected.
4. Route stability: NOT QUALIFIED. Margin `0.0037577340955934346`; `B8+B9` `0.006699346855579422`; safety factor `0.5609105150995247`.
5. Historical overlap: adequately bounded. Exact hash reproduction and path isolation establish provenance; input-independent bias plausibly explains recurrence but is not itself proof.
6. Validator identity: PASS through the immutable amendment.
7. Payload ledger: PASS, reconstructed as 25 before recovery and 37 after.
8. Downstream stop: PASS. Quantization, slice, shared-expert, dispatch, Q6_K, and M1-F work did not advance.

## Conclusion

The recovery and retention repair are ready for independent adversarial review. The accepted M1-F0 route remains valid oracle evidence, but the current input is not admissible for production M1-F recomputation. A future reviewed phase must freeze a new independent input and perform fresh M1-F0 discovery; it must not weaken this contract or reuse this unstable route for M1-F.
