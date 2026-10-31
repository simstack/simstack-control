import json

import pytest

from simstack_control.schema_walk import collect_model_schemas


def test_collects_table_schema_and_nested_table_schema():
    parent = {
        "title": "Parent",
        "type": "object",
        "properties": {"child": {"$ref": "#/$defs/Child"}},
        "$defs": {"Child": {"title": "Child", "type": "object", "properties": {}}},
    }
    child = {
        "title": "Child",
        "type": "object",
        "properties": {"part": {"$ref": "#/$defs/Part"}},
        "$defs": {"Part": {"title": "Part", "type": "object", "properties": {}}},
    }
    part = {"title": "Part", "type": "object", "properties": {"value": {"type": "number"}}}
    collected = collect_model_schemas(
        "Parent",
        {
            "Parent": json.dumps(parent),
            "Child": json.dumps(child),
            "Part": json.dumps(part),
        },
    )
    assert list(collected) == ["Parent", "Child", "Part"]
    assert collected["Child"]["title"] == "Child"
    assert "part" in collected["Child"]["properties"]


def test_uses_inline_schema_when_submodel_is_not_registered():
    parent = {
        "title": "Parent",
        "properties": {"child": {"$ref": "#/$defs/Child"}},
        "$defs": {
            "Child": {"title": "Child", "type": "object", "properties": {"n": {"type": "integer"}}},
            "Kind": {"title": "Kind", "enum": ["a", "b"]},
        },
    }
    collected = collect_model_schemas("Parent", {"Parent": json.dumps(parent)})
    assert set(collected) == {"Parent", "Child"}
    assert collected["Child"]["properties"]["n"]["type"] == "integer"


def test_missing_root_model_raises():
    with pytest.raises(ValueError, match="not in the model table"):
        collect_model_schemas("Missing", {})


def test_inline_schema_fills_a_registered_model_without_its_own_schema():
    parent = {
        "title": "Parent",
        "properties": {"child": {"$ref": "#/$defs/Child"}},
        "$defs": {"Child": {"type": "object", "properties": {"n": {"type": "integer"}}}},
    }
    collected = collect_model_schemas(
        "Parent",
        {"Parent": json.dumps(parent), "Child": None},
    )
    assert collected["Child"]["properties"]["n"]["type"] == "integer"


def test_registered_model_without_schema_or_inline_definition_raises():
    parent = {
        "title": "Parent",
        "properties": {"child": {"$ref": "#/$defs/Child"}},
    }
    with pytest.raises(ValueError, match="Child has no json_schema"):
        collect_model_schemas(
            "Parent",
            {"Parent": json.dumps(parent), "Child": None},
        )


def test_cycle_is_emitted_once():
    left = {
        "title": "Left",
        "type": "object",
        "properties": {"right": {"$ref": "#/$defs/Right"}},
    }
    right = {
        "title": "Right",
        "type": "object",
        "properties": {"left": {"$ref": "#/$defs/Left"}},
    }
    collected = collect_model_schemas(
        "Left",
        {"Left": json.dumps(left), "Right": json.dumps(right)},
    )
    assert set(collected) == {"Left", "Right"}


def test_external_reference_raises():
    parent = {"properties": {"other": {"$ref": "https://example.com/schema.json"}}}
    with pytest.raises(ValueError, match="Unsupported schema reference"):
        collect_model_schemas("Parent", {"Parent": json.dumps(parent)})
