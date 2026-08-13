import os

SERVICE_NAME = os.getenv("POWERTOOLS_SERVICE_NAME", "students-api")
METRICS_NAMESPACE = os.getenv(
    "POWERTOOLS_METRICS_NAMESPACE",
    "ServerlessStudentManager",
)
