import json
from pathlib import Path

import pytest

from submit_orca import build_orca_submit_input, build_parser

ROOT = Path(__file__).resolve().parents[1]


def example_parameters():
    return json.loads((ROOT / "examples" / "orca.json").read_text(encoding="utf-8"))


def water_xyz():
    return (ROOT / "examples" / "water.xyz").read_text(encoding="utf-8")


def root_orca_input():
    return json.loads((ROOT / "orca_input.json").read_text(encoding="utf-8"))


def test_example_matches_root_orca_input():
    assert build_orca_submit_input(example_parameters(), water_xyz()) == root_orca_input()


def test_states_and_focus_states_are_added_to_the_root_document():
    parameters = example_parameters()
    parameters["states"] = 5
    parameters["focus-states"] = 2
    expected = root_orca_input()
    expected["qm_input"]["states"] = 5
    expected["qm_input"]["focus_state"] = 2
    assert build_orca_submit_input(parameters, water_xyz()) == expected


def test_parser_reads_parameters_and_molecule():
    args = build_parser().parse_args(
        ["--parameters", "orca.json", "--resource", "jusuf", "molecule.xyz"]
    )
    assert args.parameters == "orca.json"
    assert args.resource == "jusuf"
    assert args.molecule == "molecule.xyz"
    assert args.custom_name is None
    assert args.category is None


def test_parameters_must_not_carry_a_molecule():
    parameters = root_orca_input()
    with pytest.raises(ValueError, match="must not contain a molecule"):
        build_orca_submit_input(parameters, water_xyz())


def test_missing_functional_is_rejected():
    parameters = example_parameters()
    del parameters["functional"]
    with pytest.raises(ValueError, match="missing functional"):
        build_orca_submit_input(parameters, water_xyz())


def test_unknown_key_is_rejected():
    parameters = example_parameters()
    parameters["basis_set"] = "def2-SVP"
    with pytest.raises(ValueError, match="unknown basis_set"):
        build_orca_submit_input(parameters, water_xyz())


def test_null_setting_is_rejected():
    parameters = example_parameters()
    parameters["functional"] = None
    with pytest.raises(ValueError, match="functional must not be null"):
        build_orca_submit_input(parameters, water_xyz())


def test_focus_states_require_excited_states():
    parameters = example_parameters()
    parameters["states"] = 4
    with pytest.raises(ValueError, match="missing focus-states"):
        build_orca_submit_input(parameters, water_xyz())
    parameters["states"] = 0
    parameters["focus-states"] = 1
    with pytest.raises(ValueError, match="focus-states requires states > 0"):
        build_orca_submit_input(parameters, water_xyz())


def test_invalid_functional_is_rejected():
    parameters = example_parameters()
    parameters["functional"] = "not-a-functional"
    with pytest.raises(ValueError, match="functional"):
        build_orca_submit_input(parameters, water_xyz())
