from collections.abc import Callable
from typing import Any

from aws_lambda_powertools.utilities.idempotency import (
    BasePersistenceLayer,
    IdempotencyConfig,
    idempotent_function,
)
from aws_lambda_powertools.utilities.idempotency.exceptions import (
    IdempotencyAlreadyInProgressError,
    IdempotencyValidationError,
)
from aws_lambda_powertools.utilities.typing import LambdaContext

from students_api.errors import IdempotencyKeyReusedError, OperationInProgressError

_lambda_context: LambdaContext | None = None
_configs: list[IdempotencyConfig] = []


def set_lambda_context(context: LambdaContext) -> None:
    global _lambda_context
    _lambda_context = context
    for config in _configs:
        config.register_lambda_context(context)


class CreateStudentIdempotency:
    def __init__(self, persistence: BasePersistenceLayer) -> None:
        self._config = IdempotencyConfig(
            event_key_jmespath="[environment, actorId, operation, idempotencyKey]",
            payload_validation_jmespath="payload",
            expires_after_seconds=86400,
            hash_function="sha256",
            raise_on_no_idempotency_key=True,
        )
        if _lambda_context is not None:
            self._config.register_lambda_context(_lambda_context)
        _configs.append(self._config)
        self._execute = idempotent_function(
            data_keyword_argument="data",
            persistence_store=persistence,
            config=self._config,
            key_prefix="create-student",
        )(self._invoke)

    def execute(
        self,
        *,
        data: dict[str, Any],
        action: Callable[[], dict[str, object]],
    ) -> dict[str, object]:
        try:
            result = self._execute(data=data, action=action)
        except IdempotencyValidationError:
            raise IdempotencyKeyReusedError from None
        except IdempotencyAlreadyInProgressError:
            raise OperationInProgressError from None
        if not isinstance(result, dict):
            raise RuntimeError("Idempotency returned an invalid response")
        return result

    @staticmethod
    def _invoke(
        *,
        data: dict[str, Any],
        action: Callable[[], dict[str, object]],
    ) -> dict[str, object]:
        del data
        return action()
