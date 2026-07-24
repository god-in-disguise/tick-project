# Backend

Production MVP backend scaffold.

The local MVP proved the venue behavior. This backend should extract that behavior into durable primitives:

- `TradeIntent`
- `ExecutionAttempt`
- `Position`
- `VenueEvent`
- `Reconciliation`
- `WalletAccount`
- `LedgerEvent`

The first real implementation should extract the gTrade connector from `../../local-mvp/tick-mvp-local/backend/connectors/` without copying local SQLite/threading assumptions.

