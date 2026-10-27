### Guard decision latency (offline: PayPal simulator, detector keyword, 300 decisions)

| Step | p50 | p95 | mean |
|---|---|---|---|
| PayPal order read | 0.01 ms | 0.02 ms | 0.02 ms |
| Risk assessment | 0.01 ms | 0.01 ms | 0.01 ms |
| Full guard decision | 1.07 ms | 1.43 ms | 1.16 ms |

Sequential throughput on one worker: 863.2 decisions/s
