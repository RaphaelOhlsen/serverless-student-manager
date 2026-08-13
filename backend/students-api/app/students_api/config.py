import os

SERVICE_NAME = os.getenv("POWERTOOLS_SERVICE_NAME", "students-api")
METRICS_NAMESPACE = os.getenv(
    "POWERTOOLS_METRICS_NAMESPACE",
    "ServerlessStudentManager",
)


def get_students_table_name() -> str:
    table_name = os.getenv("STUDENTS_TABLE_NAME")

    if not table_name:
        raise RuntimeError("STUDENTS_TABLE_NAME environment variable is required")

    return table_name
