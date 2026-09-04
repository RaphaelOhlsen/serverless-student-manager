from typing import Any

from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

from users_api.config import METRICS_NAMESPACE, SERVICE_NAME
from users_api.routes.activation import register_activation_routes
from users_api.routes.self_profile import register_self_profile_routes

logger = Logger(service=SERVICE_NAME)
metrics = Metrics(namespace=METRICS_NAMESPACE, service=SERVICE_NAME)
app = APIGatewayHttpResolver()

register_activation_routes(app)
register_self_profile_routes(app)


@logger.inject_lambda_context(
    correlation_id_path=correlation_paths.API_GATEWAY_HTTP,
    log_event=False,
)
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(
    event: dict[str, Any],
    context: LambdaContext,
) -> dict[str, Any]:
    metrics.add_metric(name="UsersApiInvocations", unit=MetricUnit.Count, value=1)
    return app.resolve(event, context)
