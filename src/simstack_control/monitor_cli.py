import argparse
import asyncio
import sys

from simstack_control.jsonutil import write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List SimStack jobs for this database user.")
    parser.add_argument("--id", help="Keep the job with this uuid.")
    parser.add_argument("--ids", help="Keep these uuids, separated by commas.")
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


def job_ids(single: str | None, many: str | None):
    from bson import ObjectId
    from bson.errors import InvalidId

    if single is not None and many is not None:
        raise ValueError("Use either --id or --ids")
    if single is None and many is None:
        return None
    if single is not None:
        text = single.strip()
        if text == "":
            raise ValueError("--id must be a non-empty uuid")
        parts = [text]
    else:
        parts = [part.strip() for part in many.split(",")]
        if many.strip() == "" or any(part == "" for part in parts):
            raise ValueError("--ids must be a comma-separated list of uuids")
        if len(parts) != len(set(parts)):
            raise ValueError("--ids contains a duplicate uuid")
    parsed = []
    for part in parts:
        try:
            parsed.append(ObjectId(part))
        except InvalidId as exc:
            raise ValueError(f"Invalid uuid {part!r}") from exc
    return parsed


def job_summary(document: dict) -> dict:
    document_id = document.get("_id")
    if document_id is None:
        raise ValueError("NodeRegistry document has no _id")
    if "name" not in document:
        raise ValueError(f"NodeRegistry {document_id} has no name")
    if "status" not in document:
        raise ValueError(f"NodeRegistry {document_id} has no status")
    return {
        "uuid": str(document_id),
        "name": document["name"],
        "custom_name": document["custom_name"] if "custom_name" in document else None,
        "category": document["category"] if "category" in document else None,
        "status": document["status"],
    }


async def _main() -> None:
    args = build_parser().parse_args()
    if args.node_name is not None and args.node_name.strip() == "":
        raise ValueError("--node-name must be a non-empty string")
    selected = job_ids(args.id, args.ids)
    status = parse_status(args.status)

    from simstack.models import NodeRegistry

    from simstack_control.session import simstack_session

    query: dict = {}
    if selected is not None:
        query["_id"] = {"$in": selected}
    if args.node_name is not None:
        query["name"] = args.node_name
    if status is not None:
        query["status"] = status.value

    async with simstack_session() as context:
        cursor = (
            context.db.collection(NodeRegistry)
            .find(query, {"name": 1, "custom_name": 1, "category": 1, "status": 1})
            .sort("created_at", -1)
        )
        summaries = [job_summary(document) async for document in cursor]
    if selected is None:
        write_json(summaries)
        return
    by_uuid = {item["uuid"]: item for item in summaries}
    missing = [str(item) for item in selected if str(item) not in by_uuid]
    if missing:
        raise ValueError("No job matched " + ", ".join(missing))
    write_json([by_uuid[str(item)] for item in selected])


def main() -> None:
    try:
        asyncio.run(_main())
    except (ValueError, LookupError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
