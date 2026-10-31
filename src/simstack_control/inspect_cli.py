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


def main() -> None:
    try:
        asyncio.run(_main())
    except (ValueError, LookupError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
