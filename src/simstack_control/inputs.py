from typing import Any


def require_input_document(payload: Any, names: list[str]) -> dict[str, Any]:
    """Require ``payload`` to contain exactly the node's input names."""
    if not isinstance(payload, dict):
        raise ValueError("inputs.json must be a JSON object keyed by input name")
    missing = [name for name in names if name not in payload]
    extra = [name for name in payload if name not in names]
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing {missing}")
        if extra:
            details.append(f"unexpected {extra}")
        raise ValueError(
            "inputs.json keys must match the node inputs: " + "; ".join(details)
        )
    for name in names:
        if not isinstance(payload[name], dict):
            raise ValueError(f"Input {name} must be a JSON object")
    return payload
