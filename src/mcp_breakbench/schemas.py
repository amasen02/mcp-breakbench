from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator, SchemaError
from jsonschema.validators import validator_for


class UnsafeSchemaReference(ValueError):
    pass


def _nonlocal_reference(value: Any, path: tuple[str, ...] = ()) -> tuple[str, str] | None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, str(key))
            if (
                key in {"$ref", "$dynamicRef", "$recursiveRef"}
                and isinstance(child, str)
                and not child.startswith("#")
            ):
                return "/".join(child_path), child
            found = _nonlocal_reference(child, child_path)
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _nonlocal_reference(child, (*path, str(index)))
            if found:
                return found
    return None


def reject_nonlocal_references(schema: dict[str, Any]) -> None:
    found = _nonlocal_reference(schema)
    if found:
        path, reference = found
        raise UnsafeSchemaReference(f"non-local JSON Schema reference at {path}: {reference}")


def validate_schema(schema: dict[str, Any]) -> str | None:
    try:
        reject_nonlocal_references(schema)
        cls = validator_for(schema, default=Draft202012Validator)
        cls.check_schema(schema)
    except (SchemaError, UnsafeSchemaReference) as exc:
        return str(exc.message) if isinstance(exc, SchemaError) else str(exc)
    return None


def validate_instance(schema: dict[str, Any], value: Any) -> list[str]:
    reject_nonlocal_references(schema)
    cls = validator_for(schema, default=Draft202012Validator)
    cls.check_schema(schema)
    errors = sorted(
        cls(schema).iter_errors(value),
        key=lambda e: (list(e.absolute_path), list(e.absolute_schema_path)),
    )
    return [f"{('/'.join(map(str, e.absolute_path)) or '$')}: {e.message}" for e in errors]
