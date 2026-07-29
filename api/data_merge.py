"""Defensive data merging used by recipe write paths.

Blank incoming values never erase existing data. Explicit restore/rollback
operations continue to use their reviewed, field-level before/after values.
"""


def has_meaningful_data_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def merge_preserving_existing_data(existing, incoming):
    current = existing if isinstance(existing, dict) else {}
    candidate = incoming if isinstance(incoming, dict) else {}
    merged = dict(current)

    for key, value in candidate.items():
        if not has_meaningful_data_value(value):
            continue
        if isinstance(value, dict) and isinstance(current.get(key), dict):
            merged[key] = merge_preserving_existing_data(current[key], value)
        else:
            merged[key] = value
    return merged
