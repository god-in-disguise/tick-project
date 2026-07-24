from enum import StrEnum


class TradeAction(StrEnum):
    OPEN = "open"
    CLOSE = "close"


class TradeSide(StrEnum):
    LONG = "long"
    SHORT = "short"


class TradeIntentStatus(StrEnum):
    CREATED = "created"
    VALIDATED = "validated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CONSUMED = "consumed"
    EXPIRED = "expired"


class ExecutionAttemptStatus(StrEnum):
    CREATED = "created"
    SIGNED = "signed"
    BROADCAST_PENDING = "broadcast_pending"
    BROADCAST = "broadcast"
    INITIATION_CONFIRMED = "initiation_confirmed"
    AWAITING_VENUE_EXECUTION = "awaiting_venue_execution"
    VENUE_EXECUTED = "venue_executed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    UNKNOWN = "unknown"
    RECONCILED = "reconciled"


class PositionStatus(StrEnum):
    OPENING = "opening"
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    LIQUIDATED = "liquidated"
    UNKNOWN = "unknown"


class ReconciliationStatus(StrEnum):
    PENDING = "pending"
    VENUE_ACCOUNTED = "venue_accounted"
    WALLET_RECONCILED = "wallet_reconciled"
    MISMATCHED = "mismatched"


class VenueEventType(StrEnum):
    INTENT_CREATED = "intent_created"
    EXECUTION_CREATED = "execution_created"
    TRANSACTION_SIGNED = "transaction_signed"
    TRANSACTION_BROADCAST = "transaction_broadcast"
    RECEIPT_OBSERVED = "receipt_observed"
    CALLBACK_LOG_OBSERVED = "callback_log_observed"
    REGISTER_TRADE_OBSERVED = "register_trade_observed"
    UNREGISTER_TRADE_OBSERVED = "unregister_trade_observed"
    SNAPSHOT_PRESENT = "snapshot_present"
    SNAPSHOT_ABSENT = "snapshot_absent"
    BALANCE_OBSERVED = "balance_observed"
    STOP_LOSS_OBSERVED = "stop_loss_observed"
    LIQUIDATION_OBSERVED = "liquidation_observed"
    DEEP_REORG_OBSERVED = "deep_reorg_observed"
    REDUCER_APPLIED = "reducer_applied"


POSITION_TRANSITIONS: dict[PositionStatus, set[PositionStatus]] = {
    PositionStatus.OPENING: {PositionStatus.OPEN, PositionStatus.CLOSED, PositionStatus.LIQUIDATED, PositionStatus.UNKNOWN},
    PositionStatus.OPEN: {PositionStatus.CLOSING, PositionStatus.CLOSED, PositionStatus.LIQUIDATED, PositionStatus.UNKNOWN},
    PositionStatus.CLOSING: {PositionStatus.CLOSED, PositionStatus.LIQUIDATED, PositionStatus.UNKNOWN},
    PositionStatus.UNKNOWN: {PositionStatus.OPENING, PositionStatus.OPEN, PositionStatus.CLOSING, PositionStatus.CLOSED, PositionStatus.LIQUIDATED},
    PositionStatus.CLOSED: set(),
    PositionStatus.LIQUIDATED: set(),
}

EXECUTION_TRANSITIONS: dict[ExecutionAttemptStatus, set[ExecutionAttemptStatus]] = {
    ExecutionAttemptStatus.CREATED: {ExecutionAttemptStatus.SIGNED, ExecutionAttemptStatus.FAILED, ExecutionAttemptStatus.TIMED_OUT},
    ExecutionAttemptStatus.SIGNED: {ExecutionAttemptStatus.BROADCAST_PENDING, ExecutionAttemptStatus.FAILED, ExecutionAttemptStatus.UNKNOWN},
    ExecutionAttemptStatus.BROADCAST_PENDING: {ExecutionAttemptStatus.BROADCAST, ExecutionAttemptStatus.INITIATION_CONFIRMED, ExecutionAttemptStatus.UNKNOWN},
    ExecutionAttemptStatus.BROADCAST: {ExecutionAttemptStatus.INITIATION_CONFIRMED, ExecutionAttemptStatus.FAILED, ExecutionAttemptStatus.UNKNOWN},
    ExecutionAttemptStatus.INITIATION_CONFIRMED: {
        ExecutionAttemptStatus.AWAITING_VENUE_EXECUTION,
        ExecutionAttemptStatus.VENUE_EXECUTED,
        ExecutionAttemptStatus.FAILED,
        ExecutionAttemptStatus.UNKNOWN,
    },
    ExecutionAttemptStatus.AWAITING_VENUE_EXECUTION: {
        ExecutionAttemptStatus.VENUE_EXECUTED,
        ExecutionAttemptStatus.FAILED,
        ExecutionAttemptStatus.TIMED_OUT,
        ExecutionAttemptStatus.UNKNOWN,
    },
    ExecutionAttemptStatus.VENUE_EXECUTED: {ExecutionAttemptStatus.RECONCILED},
    ExecutionAttemptStatus.UNKNOWN: {
        ExecutionAttemptStatus.BROADCAST,
        ExecutionAttemptStatus.INITIATION_CONFIRMED,
        ExecutionAttemptStatus.AWAITING_VENUE_EXECUTION,
        ExecutionAttemptStatus.VENUE_EXECUTED,
        ExecutionAttemptStatus.FAILED,
        ExecutionAttemptStatus.TIMED_OUT,
    },
    ExecutionAttemptStatus.FAILED: set(),
    ExecutionAttemptStatus.TIMED_OUT: set(),
    ExecutionAttemptStatus.RECONCILED: set(),
}


def can_transition(current: PositionStatus, target: PositionStatus) -> bool:
    return target in POSITION_TRANSITIONS[current]


def can_execution_transition(current: ExecutionAttemptStatus, target: ExecutionAttemptStatus) -> bool:
    return target in EXECUTION_TRANSITIONS[current]

