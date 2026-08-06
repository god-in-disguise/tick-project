# Avantis ZFP Optimized Matrix

Samples: 19. Each sample used $10 BTC/USD ZFP with a one-second hold.

| Leverage | Side | Open preconfirm | Open visible | Close preconfirm | Close visible | Seal after visible | Execution adjustment | Closing fee | Actual result |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 75x | short | 464.1 ms | 3.385 s | 763.6 ms | 3.995 s | 1184.2 ms | $0.150088 | $0.000000 | $-0.138550 |
| 75x | short | 450.7 ms | 2.975 s | 438.8 ms | 2.989 s | 1245.9 ms | $0.150088 | $0.000000 | $-0.151983 |
| 75x | short | 469.6 ms | 3.946 s | 604.6 ms | 3.856 s | 1188.5 ms | $0.150088 | $0.000000 | $-0.163200 |
| 75x | short | 607.2 ms | 3.784 s | 295.7 ms | 2.990 s | 1182.5 ms | $0.150088 | $0.000000 | $-0.158528 |
| 75x | short | 440.2 ms | 3.596 s | 447.5 ms | 2.982 s | 1180.0 ms | $0.150088 | $0.000000 | $-0.137611 |
| 100x | short | 444.9 ms | 3.732 s | 609.7 ms | 3.841 s | 1205.6 ms | $0.200144 | $0.000000 | $-0.190161 |
| 100x | short | 469.4 ms | 3.150 s | 798.5 ms | 4.013 s | 1219.4 ms | $0.200144 | $0.000000 | $-0.185295 |
| 100x | short | 446.6 ms | 3.542 s | 914.4 ms | 4.011 s | 1211.4 ms | $0.200144 | $0.000000 | $-0.230621 |
| 100x | short | 296.8 ms | 3.156 s | 430.4 ms | 2.985 s | 1185.4 ms | $0.200144 | $0.000000 | $-0.184133 |
| 100x | short | 532.8 ms | 3.026 s | 436.3 ms | 3.016 s | 1163.5 ms | $0.200144 | $0.000000 | $-0.213765 |
| 250x | short | 757.6 ms | 4.056 s | 430.5 ms | 2.983 s | 1252.6 ms | $0.500748 | $0.000000 | $-0.488712 |
| 250x | short | 436.2 ms | 3.394 s | 763.2 ms | 4.019 s | 1190.4 ms | $0.500748 | $0.000000 | $-0.535058 |
| 250x | short | 429.5 ms | 3.241 s | 310.7 ms | 3.000 s | 1199.6 ms | $0.500748 | $0.000000 | $-0.484420 |
| 250x | short | 455.8 ms | 3.481 s | 307.5 ms | 2.985 s | 1209.5 ms | $0.500748 | $0.000000 | $-0.518779 |
| 250x | short | 486.6 ms | 3.626 s | 444.5 ms | 3.920 s | 2798.8 ms | $0.500748 | $0.000000 | $-0.509683 |
| 500x | short | 811.9 ms | 3.978 s | 445.8 ms | 2.999 s | 1199.7 ms | $1.002791 | $0.000000 | $-0.938526 |
| 500x | short | 458.5 ms | 3.795 s | 302.9 ms | 2.984 s | 1240.9 ms | $1.002791 | $0.000000 | $-1.080267 |
| 500x | short | 345.2 ms | 2.791 s | 305.1 ms | 2.989 s | 1332.3 ms | $1.002791 | $0.000000 | $-0.971141 |
| 500x | short | 309.5 ms | 3.499 s | 955.9 ms | 3.992 s | 1203.2 ms | $1.002791 | $0.000000 | $-0.910749 |

## Cross-Sample Latency

| Metric | Min | Median | Max |
| --- | ---: | ---: | ---: |
| `openEncodeSignMs` | 6.0 ms | 11.7 ms | 16.2 ms |
| `openBroadcastResponseMs` | 211.3 ms | 233.3 ms | 665.7 ms |
| `openInitiationPreconfirmedMs` | 296.8 ms | 455.8 ms | 811.9 ms |
| `openVisibleMs` | 2791.0 ms | 3499.5 ms | 4055.8 ms |
| `closeEncodeSignMs` | 4.9 ms | 8.7 ms | 17.8 ms |
| `closeBroadcastResponseMs` | 204.6 ms | 220.3 ms | 234.8 ms |
| `closeInitiationPreconfirmedMs` | 295.7 ms | 444.5 ms | 955.9 ms |
| `closeVisibleMs` | 2982.1 ms | 2999.7 ms | 4019.1 ms |
| `closeSealAfterVisibleMs` | 1163.5 ms | 1203.2 ms | 2798.8 ms |

Four samples are enough for a first matrix, not a p95. At least 20 optimized cycles are required before setting a route SLO.
