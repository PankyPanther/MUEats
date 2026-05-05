def require_fields(data, fields):
    missing = [field for field in fields if field not in data]
    if missing:
        raise ValidationError(f"Missing required fields: {', '.join(missing)}")

def require_types(data, types):
    wrong = []
    for field, expected_type in types.items():
        if field in data and not isinstance(data[field], expected_type):
            wrong.append(f"{field} (expected {expected_type.__name__})")
    if wrong:
        raise ValidationError(", ".join(wrong))
