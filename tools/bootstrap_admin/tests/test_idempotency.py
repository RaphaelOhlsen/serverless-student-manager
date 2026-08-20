from tools.bootstrap_admin.idempotency import (
    IdempotencyConflictError,
    build_started_record,
    is_valid_state_transition,
    validate_existing_record,
)


def _build_started_record() -> dict[str, object]:
    return build_started_record(
        environment="dev",
        operation_id="operation-123",
        correlation_id="correlation-123",
        user_id="user-123",
        event_id="event-123",
        full_name="Maria da Silva",
        normalized_email="admin@example.com",
        created_at="2026-08-20T13:45:12.347Z",
        occurred_at="2026-08-20T13:45:12.347Z",
        audit_expires_at=1_779_278_400,
        actor_id="github:raphael",
        expiration=1_777_258_712,
    )


def test_build_started_record_uses_approved_physical_model() -> None:
    item = _build_started_record()

    assert item == {
        "id": "NONHTTP#dev#bootstrap-admin#first-admin#operation-123",
        "environment": "dev",
        "operation": "bootstrap-admin",
        "target": "first-admin",
        "operationId": "operation-123",
        "payloadHash": "94247984b89d9b898a0412c244823eb75387cba8187ebab790e5526297b301df",
        "state": "STARTED",
        "userId": "user-123",
        "eventId": "event-123",
        "correlationId": "correlation-123",
        "occurredAt": "2026-08-20T13:45:12.347Z",
        "auditExpiresAt": 1_779_278_400,
        "actorId": "github:raphael",
        "createdAt": "2026-08-20T13:45:12.347Z",
        "updatedAt": "2026-08-20T13:45:12.347Z",
        "expiration": 1_777_258_712,
    }


def test_started_record_does_not_persist_payload_or_client_request_token() -> None:
    item = _build_started_record()

    assert "clientRequestToken" not in item
    assert "fullName" not in item
    assert "normalizedEmail" not in item
    assert "email" not in item


def test_validate_existing_record_accepts_same_payload() -> None:
    existing = _build_started_record()

    validate_existing_record(
        existing,
        full_name="Maria da Silva",
        normalized_email="admin@example.com",
    )


def test_validate_existing_record_rejects_incompatible_payload() -> None:
    existing = _build_started_record()

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


def test_bootstrap_admin_accepts_normal_state_transitions() -> None:
    transitions = (
        ("STARTED", "COGNITO_CREATED"),
        ("COGNITO_CREATED", "PERSISTENCE_COMPLETED"),
        ("PERSISTENCE_COMPLETED", "INVITATION_SENT"),
        ("INVITATION_SENT", "COMPLETED"),
    )

    for current_state, next_state in transitions:
        assert is_valid_state_transition(
            operation="bootstrap-admin",
            current_state=current_state,
            next_state=next_state,
        )


def test_bootstrap_admin_accepts_exceptional_state_transitions() -> None:
    transitions = (
        ("STARTED", "RECONCILIATION_REQUIRED"),
        ("COGNITO_CREATED", "COMPENSATED"),
        ("COGNITO_CREATED", "RECONCILIATION_REQUIRED"),
        ("PERSISTENCE_COMPLETED", "RECONCILIATION_REQUIRED"),
        ("INVITATION_SENT", "RECONCILIATION_REQUIRED"),
    )

    for current_state, next_state in transitions:
        assert is_valid_state_transition(
            operation="bootstrap-admin",
            current_state=current_state,
            next_state=next_state,
        )


def test_bootstrap_admin_terminal_states_have_no_outgoing_transitions() -> None:
    for current_state in ("COMPLETED", "COMPENSATED", "RECONCILIATION_REQUIRED"):
        assert not is_valid_state_transition(
            operation="bootstrap-admin",
            current_state=current_state,
            next_state="STARTED",
        )


def test_resume_first_admin_invitation_accepts_approved_transitions() -> None:
    assert is_valid_state_transition(
        operation="resume-first-admin-invitation",
        current_state="STARTED",
        next_state="COMPLETED",
    )
    assert is_valid_state_transition(
        operation="resume-first-admin-invitation",
        current_state="STARTED",
        next_state="RECONCILIATION_REQUIRED",
    )


def test_resume_first_admin_invitation_rejects_bootstrap_only_states() -> None:
    for next_state in ("COGNITO_CREATED", "PERSISTENCE_COMPLETED", "INVITATION_SENT"):
        assert not is_valid_state_transition(
            operation="resume-first-admin-invitation",
            current_state="STARTED",
            next_state=next_state,
        )


def test_resume_first_admin_invitation_terminal_states_have_no_outgoing_transitions() -> None:
    for current_state in ("COMPLETED", "RECONCILIATION_REQUIRED"):
        assert not is_valid_state_transition(
            operation="resume-first-admin-invitation",
            current_state=current_state,
            next_state="STARTED",
        )


def test_bootstrap_admin_rejects_direct_completion_from_started() -> None:
    assert not is_valid_state_transition(
        operation="bootstrap-admin",
        current_state="STARTED",
        next_state="COMPLETED",
    )


def test_unknown_operation_has_no_valid_transitions() -> None:
    assert not is_valid_state_transition(
        operation="unknown-operation",
        current_state="STARTED",
        next_state="COMPLETED",
    )
