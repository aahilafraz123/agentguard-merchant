### Guard decision latency (sandbox: PayPal sandbox, detector claude-haiku-5-5, 20 decisions)

| Step | p50 | p95 | mean |
|---|---|---|---|
| PayPal order read | 844 ms | 1474 ms | 1116 ms |
| Risk assessment | 1578 ms | 1717 ms | 1598 ms |
| Full guard decision | 2446 ms | 2654 ms | 2419 ms |

Sequential throughput on one worker: 0.4 decisions/s
