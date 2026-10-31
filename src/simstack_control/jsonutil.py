import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from bson import ObjectId
from pydantic import BaseModel


def to_jsonable(value: Any) -> Any:
    """Convert database values into objects ``json.dumps`` can encode."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, BaseModel):
        return to_jsonable(value.model_dump())
    if isinstance(value, bytes):
        return {"byte_length": len(value)}
    raise ValueError(f"Cannot encode {type(value).__name__} as JSON")


def write_json(value: Any) -> None:
    print(json.dumps(to_jsonable(value), indent=2))


def load_json_file(path: str) -> Any:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
