import argparse
import asyncio
import inspect
import sys

from simstack_control.inputs import require_input_document
from simstack_control.jsonutil import load_json_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a submitted NodeRegistry entry and print its id."
    )
    parser.add_argument("--node-name", required=True, help="Node name in the node table.")
    parser.add_argument("--resource", required=True, help="Execution resource.")
    parser.add_argument("--custom-name", help="Optional display name.")
    parser.add_argument("--category", help="Optional category.")
    parser.add_argument("inputs", help="JSON object keyed by the node's input names.")
    return parser


def _nonempty_optional(flag: str, value: str | None) -> str | None:
    if value is None:
        return None
    if value.strip() == "":
        raise ValueError(f"{flag} must be a non-empty string")
    return value


async def _main() -> None:
    args = build_parser().parse_args()
    if args.node_name.strip() == "":
        raise ValueError("--node-name must be a non-empty string")
    if args.resource.strip() == "":
        raise ValueError("--resource must be a non-empty string")
    custom_name = _nonempty_optional("--custom-name", args.custom_name)
    category = _nonempty_optional("--category", args.category)
    document = load_json_file(args.inputs)

    from odmantic import Model
    from simstack.core.definitions import TaskStatus
    from simstack.core.node import compute_arg_hash
    from simstack.models import NodeRegistry, Project
    from simstack.models.models import NodeModel
    from simstack.models.named_data_reference import NamedDataReference
    from simstack.models.parameters import Parameters
    from simstack.util.importer import import_class, import_function

    from simstack_control.session import simstack_session

    async with simstack_session() as context:
        node_model = None
        if context.node_mappings is not None:
            node_model = context.node_mappings.get_by_name(args.node_name)
        if node_model is None:
            node_model = await context.db.find_one(
                NodeModel, NodeModel.name == args.node_name
            )
        if node_model is None:
            raise ValueError(f"Node {args.node_name} is not in the node table")

        wrapped = await import_function(node_model.function_mapping, context.db)
        if wrapped is None:
            raise ValueError(f"Cannot import node function {node_model.function_mapping}")
        func = wrapped._inner if hasattr(wrapped, "_inner") else wrapped
        parameter_names = []
        for name, parameter in inspect.signature(func).parameters.items():
            if parameter.kind == inspect.Parameter.VAR_KEYWORD:
                continue
            if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
                raise ValueError(
                    f"Node {args.node_name} has *{name}; inputs.json cannot bind it"
                )
            parameter_names.append(name)
        mapping_names = [item.name for item in node_model.input_mappings]
        if parameter_names != mapping_names:
            raise ValueError(
                f"Node {args.node_name} input mappings {mapping_names} "
                f"do not match function parameters {parameter_names}"
            )
        inputs = require_input_document(document, mapping_names)

        instances = []
        for item in node_model.input_mappings:
            model_class = await import_class(item.mapping, context.db)
            if model_class is None:
                raise ValueError(
                    f"Cannot import model {item.mapping} for input {item.name}"
                )
            if hasattr(model_class, "from_dict"):
                instance = model_class.from_dict(inputs[item.name])
            else:
                instance = model_class.model_validate(inputs[item.name])
            if not isinstance(instance, Model):
                raise ValueError(f"Input {item.name} did not produce a model")
            instances.append(instance)

        if not isinstance(node_model.default_parameters, Parameters):
            raise ValueError(f"Node {args.node_name} has no default parameters")
        parameter_data = node_model.default_parameters.model_dump()
        parameter_data["resource"] = args.resource
        parameters = Parameters.model_validate(parameter_data)
        if parameters.resource != args.resource:
            raise ValueError(f"Resource {args.resource!r} was not stored")

        arg_hash = compute_arg_hash(instances)
        references = []
        for item, instance in zip(node_model.input_mappings, instances):
            saved_input = await context.db.save(instance)
            if saved_input is None or saved_input.id is None:
                raise ValueError(f"Saving input {item.name} did not return an id")
            references.append(
                NamedDataReference.from_variable(
                    saved_input, variable_name=item.name
                )
            )

        projects = await context.db.find(Project)
        if projects is None or len(projects) == 0:
            project = Project(field_name="default")
            await context.db.save(project)
            project_id = project.id
        else:
            project_id = projects[0].id
        if project_id is None:
            raise ValueError("Cannot resolve a project id for the submitted node")

        registry = NodeRegistry(
            name=node_model.name,
            status=TaskStatus.SUBMITTED,
            custom_name=custom_name,
            category=category,
            version=getattr(func, "_node_version", None),
            project=project_id,
            call_path="." + node_model.name,
            input_references=references,
            function_hash="",
            arg_hash=arg_hash,
            func_mapping=node_model.function_mapping,
            is_async=asyncio.iscoroutinefunction(func),
            parameters=parameters,
        )
        saved = await context.db.save(registry)
        if saved is None or saved.id is None:
            raise ValueError(f"Saving node {args.node_name} did not return an id")
        print(saved.id)


def main() -> None:
    try:
        asyncio.run(_main())
    except (ValueError, LookupError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
