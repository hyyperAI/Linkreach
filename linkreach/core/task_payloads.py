"""Small, shared validation boundary for JSON-backed task payloads."""
from __future__ import annotations

from collections.abc import Mapping


class InvalidTaskPayload(ValueError):
    """A queued task is missing a required or correctly typed value."""


def payload_mapping(payload) -> Mapping:
    if not isinstance(payload, Mapping):
        raise InvalidTaskPayload("Task payload must be a JSON object.")
    return payload


def required_int(payload, key: str) -> int:
    value = payload_mapping(payload).get(key)
    if isinstance(value, bool):
        raise InvalidTaskPayload(f"Task payload {key!r} must be an integer.")
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidTaskPayload(f"Task payload is missing a valid {key!r}.") from exc
    if value <= 0:
        raise InvalidTaskPayload(f"Task payload {key!r} must be positive.")
    return value


def optional_int(payload, key: str) -> int | None:
    value = payload_mapping(payload).get(key)
    if value in (None, ""):
        return None
    return required_int(payload, key)


def required_text(payload, key: str, *, max_length: int | None = None) -> str:
    value = payload_mapping(payload).get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidTaskPayload(f"Task payload is missing a valid {key!r}.")
    value = value.strip()
    if max_length is not None and len(value) > max_length:
        raise InvalidTaskPayload(
            f"Task payload {key!r} exceeds {max_length:,} characters."
        )
    return value
