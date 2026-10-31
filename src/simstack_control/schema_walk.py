import json
from typing import Any


def collect_model_schemas(
    root_name: str, schemas_by_name: dict[str, str | None]
) -> dict[str, Any]:
    """Return the root model schema and every nested model schema.

    ``schemas_by_name`` holds raw ``json_schema`` strings from the model table.
    A name maps to ``None`` when that row exists but has no schema. Names that
    are absent are not registered models.

    A registered row with a schema is preferred. Otherwise a nested ``$defs``
    object stored inside a parent schema in the model table is used. A model
    that is registered, or requested as the root, and has neither raises
    ``ValueError``.
    """
    if root_name not in schemas_by_name:
        raise ValueError(f"Model {root_name} is not in the model table")

    collected: dict[str, Any] = {}
    visiting: set[str] = set()

    def add(name: str, inline: dict[str, Any] | None) -> None:
        if name in collected or name in visiting:
            return
        visiting.add(name)
        schema = _table_schema(name, schemas_by_name)
        if schema is None and _is_model_schema(inline):
            schema = inline
        if schema is None:
            visiting.remove(name)
            if name == root_name or name in schemas_by_name:
                raise ValueError(
                    f"Model {name} has no json_schema in the model table"
                )
            return
        collected[name] = schema
        definitions = schema.get("$defs")
        if not isinstance(definitions, dict):
            definitions = schema.get("definitions")
        if not isinstance(definitions, dict):
            definitions = {}
        for ref_name in referenced_model_names(schema):
            if ref_name == name:
                continue
            nested = definitions.get(ref_name)
            add(ref_name, nested if isinstance(nested, dict) else None)
        visiting.remove(name)

    add(root_name, None)
    if root_name not in collected:
        raise ValueError(f"Model {root_name} has no json_schema in the model table")
    return collected


def referenced_model_names(schema: Any) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                name = _model_name_from_ref(ref)
                if name not in seen:
                    seen.add(name)
                    found.append(name)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    return found


def _table_schema(name: str, schemas_by_name: dict[str, str | None]) -> dict[str, Any] | None:
    if name not in schemas_by_name:
        return None
    raw = schemas_by_name[name]
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model {name} json_schema is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"Model {name} json_schema is not a JSON object")
    return parsed


def _model_name_from_ref(ref: str) -> str:
    prefix = None
    for candidate in ("#/$defs/", "#/definitions/"):
        if ref.startswith(candidate):
            prefix = candidate
            break
    if prefix is None:
        raise ValueError(f"Unsupported schema reference {ref!r}")
    name = ref[len(prefix) :]
    if name == "" or "/" in name:
        raise ValueError(f"Unsupported schema reference {ref!r}")
    return name


def _is_model_schema(schema: dict[str, Any] | None) -> bool:
    if not isinstance(schema, dict):
        return False
    if "enum" in schema:
        return False
    return "properties" in schema or schema.get("type") == "object"
