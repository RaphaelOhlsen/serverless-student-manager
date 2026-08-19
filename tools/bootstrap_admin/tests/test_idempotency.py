from tools.bootstrap_admin.idempotency import (
    IdempotencyConflictError,
    build_started_record,
    is_valid_state_transition,
    validate_existing_record,
)


def test_build_started_record_uses_approved_physical_model() -> None:
    item = build_started_record(
        environment="dev",
        operation_id="operation-123",
        correlation_id="correlation-123",
        user_id="user-123",
        full_name="Maria da Silva",
        normalized_email="admin@example.com",
        created_at="2026-08-19T20:00:00Z",
        expiration=1784664000,
    )

    assert item == {
        "id": "NONHTTP#dev#bootstrap-admin#first-admin#operation-123",
        "environment": "dev",
        "operation": "bootstrap-admin",
        "target": "first-admin",
        "operationId": "operation-123",
        "payloadHash": "94247984b89d9b898a0412c244823eb75387cba8187ebab790e5526297b301df",
        "state": "STARTED",
        "userId": "user-123",
        "correlationId": "correlation-123",
        "createdAt": "2026-08-19T20:00:00Z",
        "updatedAt": "2026-08-19T20:00:00Z",
        "expiration": 1784664000,
    }


def test_validate_existing_record_accepts_same_payload() -> None:
    existing = build_started_record(
        environment="dev",
        operation_id="operation-123",
        correlation_id="correlation-123",
        user_id="user-123",
        full_name="Maria da Silva",
        normalized_email="admin@example.com",
        created_at="2026-08-19T20:00:00Z",
        expiration=1784664000,
    )

    validate_existing_record(
        existing,
        full_name="Maria da Silva",
        normalized_email="admin@example.com",
    )


def test_validate_existing_record_rejects_incompatible_payload() -> None:
    existing = build_started_record(
        environment="dev",
        operation_id="operation-123",
        correlation_id="correlation-123",
        user_id="user-123",
        full_name="Maria da Silva",
        normalized_email="admin@example.com",
        created_at="2026-08-19T20:00:00Z",
        expiration=1784664000,
    )

    try:
        validate_existing_record(
            existing,
            full_name="Outra Pessoa",
            normalized_email="admin@example.com",
        )
    except IdempotencyConflictError:
        pass
    else:
        raise AssertionError("expected IdempotencyConflictError")


def test_idempotency_state_transitions_follow_approved_state_machine() -> None:
    assert is_valid_state_transition("STARTED", "COGNITO_CREATED")
    assert is_valid_state_transition("COGNITO_CREATED", "PERSISTENCE_COMPLETED")
    assert is_valid_state_transition("PERSISTENCE_COMPLETED", "INVITATION_SENT")
    assert is_valid_state_transition("INVITATION_SENT", "COMPLETED")

    assert is_valid_state_transition("COGNITO_CREATED", "COMPENSATED")
    assert is_valid_state_transition("COGNITO_CREATED", "RECONCILIATION_REQUIRED")
    assert is_valid_state_transition("PERSISTENCE_COMPLETED", "RECONCILIATION_REQUIRED")

    assert not is_valid_state_transition("STARTED", "COMPLETED")
    assert not is_valid_state_transition("COMPLETED", "STARTED")
    assert not is_valid_state_transition("COMPENSATED", "COGNITO_CREATED")
