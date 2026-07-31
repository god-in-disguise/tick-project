from tick_mvp.states import ExecutionAttemptStatus, PositionStatus, can_execution_transition, can_transition


def test_position_state_machine_keeps_terminal_states_terminal() -> None:
    assert can_transition(PositionStatus.OPENING, PositionStatus.OPEN)
    assert can_transition(PositionStatus.OPEN, PositionStatus.CLOSING)
    assert can_transition(PositionStatus.CLOSING, PositionStatus.OPEN)
    assert can_transition(PositionStatus.CLOSING, PositionStatus.CLOSED)
    assert can_transition(PositionStatus.CLOSED, PositionStatus.LIQUIDATED)
    assert not can_transition(PositionStatus.CLOSED, PositionStatus.OPEN)
    assert not can_transition(PositionStatus.LIQUIDATED, PositionStatus.CLOSING)


def test_execution_state_machine_allows_ambiguity_recovery() -> None:
    assert can_execution_transition(ExecutionAttemptStatus.CREATED, ExecutionAttemptStatus.CLAIMED)
    assert can_execution_transition(ExecutionAttemptStatus.CLAIMED, ExecutionAttemptStatus.BROADCAST_PENDING)
    assert can_execution_transition(ExecutionAttemptStatus.BROADCAST_PENDING, ExecutionAttemptStatus.VENUE_EXECUTED)
    assert can_execution_transition(ExecutionAttemptStatus.BROADCAST_PENDING, ExecutionAttemptStatus.UNKNOWN)
    assert can_execution_transition(ExecutionAttemptStatus.UNKNOWN, ExecutionAttemptStatus.VENUE_EXECUTED)
    assert can_execution_transition(ExecutionAttemptStatus.VENUE_EXECUTED, ExecutionAttemptStatus.RECONCILED)
    assert not can_execution_transition(ExecutionAttemptStatus.RECONCILED, ExecutionAttemptStatus.BROADCAST)
