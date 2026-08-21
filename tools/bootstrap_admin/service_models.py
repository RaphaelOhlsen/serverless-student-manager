from dataclasses import dataclass
from typing import Literal

BootstrapTerminalState = Literal[
    "COMPLETED",
    "COMPENSATED",
    "RECONCILIATION_REQUIRED",
]

ResumeInvitationTerminalState = Literal[
    "COMPLETED",
    "RECONCILIATION_REQUIRED",
]


@dataclass(frozen=True)
class FirstAdminBootstrapConfig:
    environment: str
    user_pool_id: str
    users_table_name: str
    audit_table_name: str
    audit_retention_days: int

    def __post_init__(self) -> None:
        string_fields = (
            ("environment", self.environment),
            ("user_pool_id", self.user_pool_id),
            ("users_table_name", self.users_table_name),
            ("audit_table_name", self.audit_table_name),
        )
        for field_name, value in string_fields:
            if value == "":
                raise ValueError(f"{field_name} must be a non-empty string")

        if self.audit_retention_days <= 0:
            raise ValueError("audit_retention_days must be greater than zero")


@dataclass(frozen=True)
class BootstrapResult:
    operation_id: str
    user_id: str
    state: BootstrapTerminalState
    replayed: bool


@dataclass(frozen=True)
class ResumeInvitationResult:
    operation_id: str
    state: ResumeInvitationTerminalState
    replayed: bool
