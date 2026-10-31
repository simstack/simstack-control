import argparse
import asyncio
import sys

from simstack_control.jsonutil import write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List SimStack jobs for this database user.")
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print jobs from the database selected by simstack.toml.",
    )
    parser.add_argument("--node-name", help="Keep jobs with this node name.")
    parser.add_argument("--status", help="Keep jobs with this status.")
    return parser


def parse_status(status: str | None):
    if status is None:
        return None
    if status.strip() == "":
        raise ValueError("--status must be a non-empty string")
    from simstack.core.definitions import TaskStatus

    allowed = [item.value for item in TaskStatus]
    if status not in allowed:
        raise ValueError(
            f"Unknown status {status!r}. Allowed statuses are: {', '.join(allowed)}"
        )
    return TaskStatus(status)


async def _main() -> None:
    args = build_parser().parse_args()
    if not args.list:
        raise ValueError("simstack_monitor requires --list")
    if args.node_name is not None and args.node_name.strip() == "":
        raise ValueError("--node-name must be a non-empty string")
    status = parse_status(args.status)

    from simstack.models import NodeRegistry

    from simstack_control.session import simstack_session

    filters = []
    if args.node_name is not None:
        filters.append(NodeRegistry.name == args.node_name)
    if status is not None:
        filters.append(NodeRegistry.status == status)

    async with simstack_session() as context:
        jobs = await context.db.find(
            NodeRegistry,
            *filters,
            sort=NodeRegistry.created_at.desc(),
        )
        write_json([job.model_dump() for job in jobs])


def main() -> None:
    try:
        asyncio.run(_main())
    except (ValueError, LookupError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
