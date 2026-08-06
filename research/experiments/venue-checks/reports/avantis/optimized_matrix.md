# Avantis ZFP Optimized Matrix

Samples: 4. Each sample used $10 BTC/USD ZFP with a one-second hold.

| Leverage | Side | Open preconfirm | Open visible | Close preconfirm | Close visible | Seal after visible | Execution adjustment | Closing fee | Actual result |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 75x | short | 357.9 ms | 3.444 s | 778.4 ms | 4.017 s | 1202.6 ms | $0.150108 | $0.000000 | $-0.026791 |
| 100x | long | 490.2 ms | 3.242 s | 363.1 ms | 2.993 s | 1161.7 ms | $0.200176 | $0.000000 | $-0.203471 |
| 250x | long | 501.2 ms | 3.223 s | 757.9 ms | 4.027 s | 1167.6 ms | $0.501099 | $0.000000 | $-0.459486 |
| 500x | short | 363.4 ms | 3.465 s | 765.0 ms | 4.029 s | 1182.9 ms | $1.003661 | $0.000000 | $-1.034096 |

## Cross-Sample Latency

| Metric | Min | Median | Max |
| --- | ---: | ---: | ---: |
| `openEncodeSignMs` | 5.8 ms | 8.6 ms | 10.7 ms |
| `openBroadcastResponseMs` | 188.3 ms | 197.6 ms | 198.6 ms |
| `openInitiationPreconfirmedMs` | 357.9 ms | 426.8 ms | 501.2 ms |
| `openVisibleMs` | 3222.9 ms | 3343.1 ms | 3465.3 ms |
| `closeEncodeSignMs` | 5.0 ms | 7.9 ms | 13.5 ms |
| `closeBroadcastResponseMs` | 189.4 ms | 193.2 ms | 196.1 ms |
| `closeInitiationPreconfirmedMs` | 363.1 ms | 761.5 ms | 778.4 ms |
| `closeVisibleMs` | 2992.5 ms | 4022.2 ms | 4029.2 ms |
| `closeSealAfterVisibleMs` | 1161.7 ms | 1175.2 ms | 1202.6 ms |

## Economic Execution Boundary

The callback calldata was decoded from each live transaction. All eight legs
used `executeMarketOrders` with a signed Pyth Lazer update. The callback's
`MarketExecuted` log is the onchain state change that creates or closes the
position; Base `pendingLogs` delivered it before block seal.

| Leverage | Leg | Preconfirm -> oracle sample | Oracle sample -> callback | Gesture -> callback |
| ---: | --- | ---: | ---: | ---: |
| 75x | open | 2433.5 ms | 653.0 ms | 3444.4 ms |
| 75x | close | 2567.4 ms | 671.1 ms | 4016.9 ms |
| 100x | open | 2084.0 ms | 667.6 ms | 3241.8 ms |
| 100x | close | 1968.1 ms | 661.3 ms | 2992.5 ms |
| 250x | open | 2075.7 ms | 646.1 ms | 3222.9 ms |
| 250x | close | 2594.7 ms | 674.8 ms | 4027.5 ms |
| 500x | open | 2467.6 ms | 634.3 ms | 3465.3 ms |
| 500x | close | 2600.3 ms | 663.9 ms | 4029.2 ms |

The source price was sampled roughly 650 ms before callback observation. It is
not an earlier economic fill: execution and position mutation happen inside
the callback transaction. The dominant latency is before the signed oracle
sample, in keeper pickup and on-demand price production.

Four samples are enough for a first matrix, not a p95. At least 20 optimized cycles are required before setting a route SLO.
