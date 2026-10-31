import pytest

from simstack_control.inspect_cli import build_parser as inspect_parser
from simstack_control.monitor_cli import build_parser as monitor_parser
from simstack_control.monitor_cli import job_ids, job_summary, parse_status
from simstack_control.submit_cli import build_parser as submit_parser
from simstack_control.submit_cli import slurm_parameter_overrides


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
    args = monitor_parser().parse_args(["--node-name", "relax", "--status", "running"])
    assert args.node_name == "relax"
    assert args.status == "running"
    assert args.id is None
    assert args.ids is None


def test_monitor_parser_accepts_one_or_many_ids():
    one = monitor_parser().parse_args(["--id", "6ae5b15419ac45bec6802946"])
    assert one.id == "6ae5b15419ac45bec6802946"
    many = monitor_parser().parse_args(
        ["--ids", "6ae5b15419ac45bec6802946,6ae5b15419ac45bec6802947"]
    )
    assert many.ids == "6ae5b15419ac45bec6802946,6ae5b15419ac45bec6802947"


def test_job_ids_parses_one_and_many():
    one = job_ids("6ae5b15419ac45bec6802946", None)
    assert [str(item) for item in one] == ["6ae5b15419ac45bec6802946"]
    many = job_ids(None, "6ae5b15419ac45bec6802946, 6ae5b15419ac45bec6802947")
    assert [str(item) for item in many] == [
        "6ae5b15419ac45bec6802946",
        "6ae5b15419ac45bec6802947",
    ]
    assert job_ids(None, None) is None


def test_job_ids_rejects_bad_lists():
    with pytest.raises(ValueError, match="either --id or --ids"):
        job_ids("6ae5b15419ac45bec6802946", "6ae5b15419ac45bec6802947")
    with pytest.raises(ValueError, match="non-empty"):
        job_ids("  ", None)
    with pytest.raises(ValueError, match="comma-separated"):
        job_ids(None, "6ae5b15419ac45bec6802946,")
    with pytest.raises(ValueError, match="duplicate"):
        job_ids(None, "6ae5b15419ac45bec6802946,6ae5b15419ac45bec6802946")
    with pytest.raises(ValueError, match="Invalid uuid"):
        job_ids("not-a-uuid", None)


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
    assert args.params is None
    assert args.inputs == "inputs.json"


def test_submit_parser_accepts_params():
    args = submit_parser().parse_args(
        [
            "--node-name",
            "orca",
            "--resource",
            "justus",
            "--params",
            "params.json",
            "inputs.json",
        ]
    )
    assert args.params == "params.json"


def test_slurm_parameter_overrides_keep_only_the_given_fields():
    assert slurm_parameter_overrides({"nodes": 2, "tasks": 8}) == {
        "nodes": 2,
        "tasks": 8,
    }


def test_slurm_parameter_overrides_reject_unknown_or_empty_documents():
    with pytest.raises(ValueError, match="unknown SlurmParameters"):
        slurm_parameter_overrides({"nodes": 1, "ntasks": 4})
    with pytest.raises(ValueError, match="at least one"):
        slurm_parameter_overrides({})
    with pytest.raises(ValueError, match="JSON object"):
        slurm_parameter_overrides([{"nodes": 1}])
    with pytest.raises(ValueError, match="not valid SlurmParameters"):
        slurm_parameter_overrides({"nodes": 0})
