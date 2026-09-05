from decimal import Decimal


def normalize_dynamodb_value(value: object) -> object:
    if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        return int(value)
    if isinstance(value, dict):
        return {key: normalize_dynamodb_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_dynamodb_value(item) for item in value]
    return value
