# Avantis ZFP Optimized Matrix

Samples: 4. Each sample used $10 BTC/USD ZFP with a one-second hold.

| Leverage | Side | Open preconfirm | Open visible | Close preconfirm | Close visible | Seal after visible | Execution adjustment | Closing fee | Actual result |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 75x | short | 787.8 ms | 3.987 s | 450.2 ms | 3.011 s | 1184.3 ms | $0.150088 | $0.000000 | $-0.138206 |
| 100x | short | 477.4 ms | 3.792 s | 433.9 ms | 2.825 s | 1191.9 ms | $0.200144 | $0.000000 | $-0.203151 |
| 250x | short | 438.0 ms | 3.350 s | 456.0 ms | 2.996 s | 1632.6 ms | $0.500748 | $0.000000 | $-0.503805 |
| 500x | short | 618.1 ms | 3.898 s | 436.5 ms | 3.005 s | 1224.9 ms | $1.002791 | $0.000000 | $-1.007767 |

## Cross-Sample Latency

| Metric | Min | Median | Max |
| --- | ---: | ---: | ---: |
| `openEncodeSignMs` | 10.8 ms | 15.0 ms | 16.6 ms |
| `openBroadcastResponseMs` | 215.0 ms | 242.6 ms | 249.2 ms |
| `openInitiationPreconfirmedMs` | 438.0 ms | 547.8 ms | 787.8 ms |
| `openVisibleMs` | 3349.6 ms | 3845.1 ms | 3987.0 ms |
| `closeEncodeSignMs` | 8.0 ms | 12.0 ms | 14.4 ms |
| `closeBroadcastResponseMs` | 215.9 ms | 223.9 ms | 231.5 ms |
| `closeInitiationPreconfirmedMs` | 433.9 ms | 443.3 ms | 456.0 ms |
| `closeVisibleMs` | 2824.9 ms | 3000.4 ms | 3010.8 ms |
| `closeSealAfterVisibleMs` | 1184.3 ms | 1208.4 ms | 1632.6 ms |

Four samples are enough for a first matrix, not a p95. At least 20 optimized cycles are required before setting a route SLO.
