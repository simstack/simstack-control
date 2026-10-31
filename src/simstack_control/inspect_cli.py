import argparse
import asyncio
import json
import sys

from simstack_control.jsonutil import write_json
from simstack_control.schema_walk import collect_model_schemas


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect SimStack nodes, model schemas, and stored model documents."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--list-nodes",
        "--lists-nodes",
        action="store_true",
        help="List nodes stored in the node table.",
    )
    group.add_argument(
        "--list-models",
        action="store_true",
        help="List models stored in the model table.",
    )
    group.add_argument(
        "--dump-model",
        metavar="MODEL_NAME",
        help="Dump one model schema from the model table.",
    )
    group.add_argument(
        "--dump-model-recursive",
        metavar="MODEL_NAME",
        help="Dump a model schema and the schemas of its submodels.",
    )
    group.add_argument(
        "--model-data",
        nargs=2,
        metavar=("MODEL_NAME", "UUID"),
        help="Dump the document with this id from the model's collection.",
    )
    group.add_argument(
        "--node-id",
        metavar="UUID",
        help="Dump a job's inputs, outputs, and child job ids. File stacks are omitted.",
    )
    return parser


async def _main() -> None:
    args = build_parser().parse_args()
    from simstack.models.models import ModelMapping, NodeModel

    from simstack_control.session import simstack_session

    async with simstack_session() as context:
        if args.list_nodes:
            nodes = await context.db.find(NodeModel)
            write_json(
                [
                    {
                        "name": node.name,
                        "function_mapping": node.function_mapping,
                        "description": node.description,
                        "inputs": [
                            {"name": item.name, "mapping": item.mapping}
                            for item in node.input_mappings
                        ],
                    }
                    for node in sorted(nodes, key=lambda node: node.name)
                ]
            )
            return
        if args.list_models:
            models = await context.db.find(ModelMapping)
            write_json(
                [
                    {
                        "name": model.name,
                        "mapping": model.mapping,
                        "collection_name": model.collection_name,
                    }
                    for model in sorted(models, key=lambda model: model.name)
                ]
            )
            return
        if args.dump_model is not None:
            write_json(await _load_schema(context, args.dump_model))
            return
        if args.dump_model_recursive is not None:
            models = await context.db.find(ModelMapping)
            schemas = {model.name: model.json_schema for model in models}
            write_json(collect_model_schemas(args.dump_model_recursive, schemas))
            return
        if args.node_id is not None:
            write_json(await _load_job(context, args.node_id))
            return
        model_name, document_id = args.model_data
        write_json(await _load_model_document(context, model_name, document_id))


async def _load_schema(context, model_name: str) -> dict:
    from simstack.models.models import ModelMapping

    if model_name.strip() == "":
        raise ValueError("--dump-model must be a non-empty model name")
    matches = await context.db.find(ModelMapping, ModelMapping.name == model_name)
    if len(matches) == 0:
        raise ValueError(f"Model {model_name} is not in the model table")
    if len(matches) > 1:
        raise ValueError(f"Model {model_name} has more than one model-table row")
    raw = matches[0].json_schema
    if raw is None:
        raise ValueError(f"Model {model_name} has no json_schema in the model table")
    try:
        schema = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Model {model_name} json_schema is not valid JSON: {exc}"
        ) from exc
    if not isinstance(schema, dict):
        raise ValueError(f"Model {model_name} json_schema is not a JSON object")
    return schema


async def _load_model_document(context, model_name: str, document_id: str) -> dict:
    from bson import ObjectId
    from bson.errors import InvalidId
    from simstack.models.models import ModelMapping

    if model_name.strip() == "":
        raise ValueError("--model-data model name must be a non-empty string")
    if document_id.strip() == "":
        raise ValueError("--model-data uuid must be a non-empty string")
    matches = await context.db.find(ModelMapping, ModelMapping.name == model_name)
    if len(matches) == 0:
        raise ValueError(f"Model {model_name} is not in the model table")
    if len(matches) > 1:
        raise ValueError(f"Model {model_name} has more than one model-table row")
    collection_name = matches[0].collection_name
    if collection_name.strip() == "" or collection_name == "EmbeddedModel":
        raise ValueError(
            f"Model {model_name} is not stored in its own collection "
            f"({collection_name!r})"
        )
    try:
        object_id = ObjectId(document_id)
    except InvalidId as exc:
        raise ValueError(f"Invalid uuid {document_id!r}") from exc
    document = await context.db.collection(collection_name).find_one({"_id": object_id})
    if document is None:
        raise ValueError(
            f"No {model_name} document with uuid {document_id} in {collection_name}"
        )
    return document


_FILE_STACK_NAMES = {"FileStack", "FileList", "FileListModel", "FileListIO"}


def _unwrap_annotation(annotation):
    import types
    from typing import Union, get_args, get_origin

    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return _unwrap_annotation(args[0])
    return annotation


def _annotation_model_name(annotation) -> str | None:
    from typing import get_args, get_origin

    annotation = _unwrap_annotation(annotation)
    origin = get_origin(annotation)
    if origin in (list, tuple, set):
        args = get_args(annotation)
        if len(args) == 1:
            return _annotation_model_name(args[0])
        return None
    return getattr(annotation, "__name__", None)


def _referenced_model_fields(model_class) -> dict:
    from odmantic import EmbeddedModel, Model

    referenced = {}
    for name, field in model_class.model_fields.items():
        annotation = _unwrap_annotation(field.annotation)
        model_name = _annotation_model_name(field.annotation)
        if model_name in _FILE_STACK_NAMES:
            continue
        if (
            isinstance(annotation, type)
            and issubclass(annotation, Model)
            and not issubclass(annotation, EmbeddedModel)
        ):
            referenced[name] = annotation
    return referenced


def _file_stack_field_names(model_class) -> set[str]:
    return {
        name
        for name, field in model_class.model_fields.items()
        if _annotation_model_name(field.annotation) in _FILE_STACK_NAMES
    }


def _parse_object_id(value: str):
    from bson import ObjectId
    from bson.errors import InvalidId

    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"Invalid uuid {value!r}")
    try:
        return ObjectId(value)
    except InvalidId as exc:
        raise ValueError(f"Invalid uuid {value!r}") from exc


async def _load_job(context, node_id: str) -> dict:
    from bson import ObjectId
    from simstack.models import NodeRegistry
    from simstack.models.models import ModelMapping
    from simstack.util.importer import import_class

    object_id = _parse_object_id(node_id)
    registry = await context.db.collection(NodeRegistry).find_one({"_id": object_id})
    if registry is None:
        raise ValueError(f"Job {node_id} is not in the node registry")
    for key in ("input_references", "results_references"):
        if key not in registry:
            raise ValueError(f"Job {node_id} has no {key}")
        if not isinstance(registry[key], list):
            raise ValueError(f"Job {node_id} {key} is not a list")

    async def referenced_documents(references: list) -> list:
        loaded = []
        for reference in references:
            if not isinstance(reference, dict):
                raise ValueError(f"Job {node_id} has a reference that is not an object")
            for key in ("variable_name", "variable_mapping", "reference"):
                if key not in reference:
                    raise ValueError(f"Job {node_id} reference is missing {key}")
            mapping = reference["variable_mapping"]
            model_name = mapping.rsplit(".", 1)[-1]
            if model_name in _FILE_STACK_NAMES:
                continue
            model_row = context.model_mappings.get_by_mapping(mapping)
            if model_row is None:
                model_row = await context.db.find_one(
                    ModelMapping, ModelMapping.mapping == mapping
                )
            if model_row is None:
                raise ValueError(f"Model mapping {mapping} is not in the model table")
            if model_row.name in _FILE_STACK_NAMES:
                continue
            reference_id = reference["reference"]
            if isinstance(reference_id, str):
                reference_id = _parse_object_id(reference_id)
            elif not isinstance(reference_id, ObjectId):
                raise ValueError(
                    f"Job {node_id} reference {reference['variable_name']} has no uuid"
                )
            document = await _expand_document(
                context, model_row, reference_id, import_class
            )
            loaded.append(
                {
                    "name": reference["variable_name"],
                    "model": model_row.name,
                    "uuid": str(reference_id),
                    "data": document,
                }
            )
        return loaded

    children = []
    cursor = (
        context.db.collection(NodeRegistry)
        .find(
            {"parent_ids": {"$in": [object_id, str(object_id)]}},
            {"_id": 1},
        )
        .sort("created_at", 1)
    )
    async for child in cursor:
        if "_id" not in child:
            raise ValueError(f"Child of job {node_id} has no _id")
        children.append(str(child["_id"]))

    return {
        "uuid": str(object_id),
        "inputs": await referenced_documents(registry["input_references"]),
        "outputs": await referenced_documents(registry["results_references"]),
        "child_uuids": children,
    }


async def _expand_document(context, model_row, object_id, import_class) -> dict:
    from bson import ObjectId

    collection_name = model_row.collection_name
    if collection_name.strip() == "" or collection_name == "EmbeddedModel":
        raise ValueError(
            f"Model {model_row.name} is not stored in its own collection "
            f"({collection_name!r})"
        )
    document = await context.db.collection(collection_name).find_one({"_id": object_id})
    if document is None:
        raise ValueError(
            f"No {model_row.name} document with uuid {object_id} in {collection_name}"
        )
    model_class = await import_class(model_row.mapping, context.db)
    if model_class is None:
        raise ValueError(f"Cannot import model {model_row.mapping}")
    file_stack_fields = _file_stack_field_names(model_class)
    referenced_fields = _referenced_model_fields(model_class)
    expanded = {}
    for key, value in document.items():
        if key in file_stack_fields:
            continue
        target = referenced_fields.get(key)
        if target is not None and isinstance(value, (ObjectId, str)):
            nested_id = _parse_object_id(value) if isinstance(value, str) else value
            nested_row = context.model_mappings.get_by_name(target.__name__)
            if nested_row is None:
                from simstack.models.models import ModelMapping

                nested_row = await context.db.find_one(
                    ModelMapping, ModelMapping.name == target.__name__
                )
            if nested_row is None:
                raise ValueError(
                    f"Model {target.__name__} referenced by {model_row.name}.{key} "
                    "is not in the model table"
                )
            if nested_row.name in _FILE_STACK_NAMES:
                continue
            expanded[key] = await _expand_document(
                context, nested_row, nested_id, import_class
            )
            continue
        expanded[key] = value
    return expanded


def main() -> None:
    try:
        asyncio.run(_main())
    except (ValueError, LookupError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
