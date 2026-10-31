import argparse
import asyncio
import sys

from simstack_control.jsonutil import load_json_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Insert a model document and print its id."
    )
    parser.add_argument("--model", required=True, help="Model name in the model table.")
    parser.add_argument(
        "model_data",
        help="JSON file with the model fields.",
    )
    return parser


async def _main() -> None:
    args = build_parser().parse_args()
    if args.model.strip() == "":
        raise ValueError("--model must be a non-empty model name")
    payload = load_json_file(args.model_data)
    if not isinstance(payload, dict):
        raise ValueError(f"{args.model_data} must be a JSON object")

    from simstack.models.models import ModelMapping
    from simstack.util.importer import import_class_by_name

    from simstack_control.session import simstack_session

    async with simstack_session() as context:
        matches = await context.db.find(ModelMapping, ModelMapping.name == args.model)
        if len(matches) == 0:
            raise ValueError(f"Model {args.model} is not in the model table")
        if len(matches) > 1:
            raise ValueError(f"Model {args.model} has more than one model-table row")
        collection_name = matches[0].collection_name
        if collection_name.strip() == "" or collection_name == "EmbeddedModel":
            raise ValueError(
                f"Model {args.model} cannot be uploaded as its own document "
                f"({collection_name!r})"
            )
        model_class = await import_class_by_name(args.model, context.db)
        if hasattr(model_class, "from_dict"):
            instance = model_class.from_dict(payload)
        else:
            instance = model_class.model_validate(payload)
        saved = await context.db.save(instance)
        if saved is None or saved.id is None:
            raise ValueError(f"Saving {args.model} did not return an id")
        print(saved.id)


def main() -> None:
    try:
        asyncio.run(_main())
    except (ValueError, LookupError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
