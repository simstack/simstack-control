"""Tests for the legacy orca_scratch submit example and version handling.

The example module is imported from ``examples`` (configured via pytest's
``pythonpath``), mirroring the conventions of the removed ``submit_orca``
tests.  No database is touched.
"""

import inspect
import json
from pathlib import Path

import pytest

import submit_orca_scratch as example
from simstack_control.legacy_qm_input import build_orca_jinja_submit_input
from simstack_control.submit_cli import resolve_node_version, submit_inputs

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "examples"


def water_xyz() -> str:
    return (EXAMPLES / "water.xyz").read_text()


def water_settings() -> dict:
    return json.loads((EXAMPLES / "orca_jinja.json").read_text())


class TestParser:
    def test_defaults(self):
        args = example.build_parser().parse_args(
            ["--parameters", "x.json", "--resource", "r", "mol.xyz"]
        )
        assert args.version == example.DEFAULT_VERSION
        assert args.node_name == "orca_scratch"
        assert args.params is None

    def test_all_flags(self):
        args = example.build_parser().parse_args(
            [
                "--parameters",
                "x.json",
                "--resource",
                "justus-jinja",
                "--params",
                "p.json",
                "--custom-name",
                "smoke",
                "--category",
                "qm2",
                "--node-name",
                "custom_orca_jinja_node",
                "--version",
                "compatible_old",
                "mol.xyz",
            ]
        )
        assert args.resource == "justus-jinja"
        assert args.node_name == "custom_orca_jinja_node"
        assert args.version == "compatible_old"

    def test_builds_same_document_as_root_golden(self):
        golden = json.loads((REPO_ROOT / "orca_jinja_input.json").read_text())
        document = build_orca_jinja_submit_input(water_settings(), water_xyz())
        assert document == golden

    def test_builds_nitrobenzene_same_document_as_root_golden(self):
        golden = json.loads(
            (REPO_ROOT / "orca_jinja_nitrobenzene_input.json").read_text()
        )
        settings = json.loads((EXAMPLES / "nitrobenzene_jinja.json").read_text())
        xyz = (EXAMPLES / "nitrobenzene.xyz").read_text()
        document = build_orca_jinja_submit_input(settings, xyz)
        assert document == golden
        assert golden["qm_input"]["functional"]["functional"] == "CAM-B3LYP"
        assert golden["qm_input"]["Hyperpol"] is True

    def test_example_uses_the_legacy_builder(self):
        from simstack_control import legacy_qm_input as lqi

        assert example.build_orca_jinja_submit_input is lqi.build_orca_jinja_submit_input


class TestVersionHandling:
    def test_explicit_version_wins(self):
        func = object()
        assert resolve_node_version("compatible_old", func) == "compatible_old"

    def test_node_version_fallback(self):
        from types import SimpleNamespace

        func = SimpleNamespace(_node_version="1.2.3")
        assert resolve_node_version(None, func) == "1.2.3"

    def test_legacy_default_is_none(self):
        func = object()
        assert resolve_node_version(None, func) is None

    def test_empty_version_rejected(self):
        with pytest.raises(ValueError, match="must be a non-empty string"):
            # submit_inputs rejects empty --version after resolving internals
            from simstack_control.submit_cli import _nonempty_optional

            _nonempty_optional("--version", "   ")

    def test_submit_inputs_accepts_version_kwarg(self):
        params = inspect.signature(submit_inputs).parameters
        assert "version" in params
        assert params["version"].default is None
