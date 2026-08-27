from decimal import Decimal


def normalize_dynamodb_value(value: object) -> object:
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    return value
