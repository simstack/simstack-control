import pytest

from simstack_control.inspect_cli import build_parser as inspect_parser
from simstack_control.monitor_cli import build_parser as monitor_parser
from simstack_control.monitor_cli import job_summary, parse_status
from simstack_control.submit_cli import build_parser as submit_parser


def test_inspect_requires_one_action():
    with pytest.raises(SystemExit):
        inspect_parser().parse_args([])


def test_inspect_accepts_node_id():
    args = inspect_parser().parse_args(["--node-id", "6ae5b15419ac45bec6802946"])
    assert args.node_id == "6ae5b15419ac45bec6802946"


def test_inspect_lists_nodes_flag():
    args = inspect_parser().parse_args(["--lists-nodes"])
    assert args.list_nodes is True


def test_monitor_status_rejects_unknown_value():
    with pytest.raises(ValueError, match="Unknown status"):
        parse_status("not-a-status")
    with pytest.raises(ValueError, match="non-empty"):
        parse_status("  ")


def test_monitor_status_accepts_submitted():
    assert parse_status("submitted").value == "submitted"
    assert parse_status(None) is None


def test_monitor_parser_keeps_filters():
    args = monitor_parser().parse_args(
        ["--list", "--node-name", "relax", "--status", "running"]
    )
    assert args.list is True
    assert args.node_name == "relax"
    assert args.status == "running"


def test_job_summary_keeps_only_the_list_fields():
    summary = job_summary(
        {
            "_id": "6ae5b15419ac45bec6802946",
            "name": "orca",
            "status": "submitted",
            "parameters": {"resource": {"value": "local"}},
        }
    )
    assert summary == {
        "uuid": "6ae5b15419ac45bec6802946",
        "name": "orca",
        "custom_name": None,
        "category": None,
        "status": "submitted",
    }


def test_submit_parser_optional_flags():
    args = submit_parser().parse_args(
        ["--node-name", "relax", "--resource", "jusuf", "inputs.json"]
    )
    assert args.custom_name is None
    assert args.category is None
    assert args.inputs == "inputs.json"
