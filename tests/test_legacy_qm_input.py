"""Tests for the legacy orca_jinja QMInput document builder.

These tests run without a database: they pin the exact document shape that
the legacy simstack-model runner on justus reads from the production DB
(the de-facto schema of ``molecular_qm_models.qm_input.QMInput``).
"""

import json
from pathlib import Path

import pytest

from simstack_control.legacy_qm_input import (
    build_legacy_qm_input,
    build_orca_jinja_submit_input,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "examples"


def wa_xyz() -> str:
    return (EXAMPLES / "water.xyz").read_text()


def water_settings(**overrides) -> dict:
    settings = {
        "basis-set": "def2-SVP",
        "aux-basis": "none",
        "functional": "B3LYP",
        "dispersion": "D3",
        "method": "DFT",
        "charge": 0,
        "multiplicity": 1,
        "optimization": False,
    }
    settings.update(overrides)
    return settings


def build(**settings) -> dict:
    return build_legacy_qm_input(water_settings(**settings), wa_xyz())


class TestGoldenDocument:
    def test_matches_root_golden_file(self):
        golden = json.loads((REPO_ROOT / "orca_jinja_input.json").read_text())
        document = build_orca_jinja_submit_input(water_settings(), wa_xyz())
        assert document == golden

    def test_water_molecule_atoms(self):
        molecule = build()["molecule"]
        assert molecule["field_name"] == "Molecule"
        assert [(a["element"], a["x"], a["y"], a["z"]) for a in molecule["atoms"]] == [
            ("O", 0.0, 0.0, 0.117),
            ("H", 0.0, 0.755, -0.471),
            ("H", 0.0, -0.755, -0.471),
        ]
        assert all(
            a["field_name"] == "Atom" and a["properties"] == {}
            for a in molecule["atoms"]
        )

    def test_full_schema_is_explicit(self):
        expected_legacy_fields = {
            "field_name",
            "molecule",
            "charge",
            "multiplicity",
            "open_shell_calculation",
            "basis_set",
            "functional",
            "method",
            "gradients",
            "optimization",
            "frequencies",
            "solvent",
            "solvent_model",
            "print_level",
            "scf_accuracy",
            "optimization_accuracy",
            "grid_type",
            "grid_spacing",
            "max_scf_iterations",
            "max_optimization_iterations",
            "first_line",
            "blocks",
            "Dipole",
            "Quadrupole",
            "Polar",
            "Hyperpol",
            "HyperpolFrequencynm",
            "PolarVelocity",
            "PolarDipQuad",
            "PolarQuadQuad",
            "states",
            "focus_state",
            "active_electrons",
            "active_orbitals",
            "restart_files",
            "tolerate_failure",
            "use_solvent",
            "excited_states",
            "compute_properties",
            "non_standard_inputs",
            "non_standard_parameters",
        }
        built = build()
        assert set(built) == expected_legacy_fields
        assert built["basis_set"] == {
            "field_name": "BasisSet",
            "basis_set": "def2-SVP",
            "aux_basis": {"field_name": "AuxBasis", "aux_basis": "none"},
        }
        assert built["functional"] == {
            "field_name": "Functional",
            "functional": "B3LYP",
            "dispersion_correction": {
                "field_name": "DispersionCorrection",
                "value": "D3",
            },
        }
        assert built["restart_files"] == {"elements": []}


class TestNitrobenzeneGolden:
    """Golden test for the opt + freq + dipol + hyperpol smoke-test input."""

    def test_matches_root_golden_file(self):
        golden = json.loads(
            (REPO_ROOT / "orca_jinja_nitrobenzene_input.json").read_text()
        )
        settings = json.loads((EXAMPLES / "nitrobenzene_jinja.json").read_text())
        xyz = (EXAMPLES / "nitrobenzene.xyz").read_text()
        document = build_orca_jinja_submit_input(settings, xyz)
        assert document == golden

    def test_calculation_features_are_forwarded(self):
        settings = json.loads((EXAMPLES / "nitrobenzene_jinja.json").read_text())
        xyz = (EXAMPLES / "nitrobenzene.xyz").read_text()
        built = build_orca_jinja_submit_input(settings, xyz)["qm_input"]
        assert built["optimization"] is True
        assert built["optimization_accuracy"] == "Medium"
        assert built["frequencies"] is True
        assert built["Dipole"] is True
        assert built["Hyperpol"] is True
        assert built["HyperpolFrequencynm"] == 1064.0
        assert built["compute_properties"] is True
        assert len(built["molecule"]["atoms"]) == 14


class TestParameterValidation:
    def test_missing_required_key(self):
        settings = water_settings()
        del settings["basis-set"]
        with pytest.raises(ValueError, match="missing basis-set"):
            build_legacy_qm_input(settings, wa_xyz())

    def test_unknown_key(self):
        with pytest.raises(ValueError, match="unknown broken"):
            build(**{"broken": 1})

    def test_null_value_rejected(self):
        with pytest.raises(ValueError, match="must not be null"):
            build(**{"method": None})

    def test_settings_must_be_object(self):
        with pytest.raises(ValueError, match="must be a JSON object"):
            build_legacy_qm_input([], wa_xyz())

    def test_molecule_key_forbidden(self):
        with pytest.raises(ValueError, match="must not contain a molecule"):
            build_legacy_qm_input(water_settings(molecule={}), wa_xyz())

    def test_charge_must_be_int(self):
        with pytest.raises(ValueError, match="charge must be an integer"):
            build(**{"charge": 1.5})

    def test_multiplicity_must_be_positive(self):
        with pytest.raises(ValueError, match="multiplicity must be >= 1"):
            build(**{"multiplicity": 0})

    def test_optimization_must_be_bool(self):
        with pytest.raises(ValueError, match="optimization must be true or false"):
            build(**{"optimization": "yes"})

    def test_optimization_requires_accuracy(self):
        with pytest.raises(ValueError, match="missing optimization-accuracy"):
            build(optimization=True)

    def test_enum_values_are_canonicalized(self):
        document = build(**{"basis-set": "def2-svp", "aux-basis": "def2/j"})
        assert document["basis_set"]["basis_set"] == "def2-SVP"
        assert document["basis_set"]["aux_basis"]["aux_basis"] == "def2/J"

    def test_invalid_aux_basis(self):
        with pytest.raises(ValueError, match="aux-basis"):
            build(**{"aux-basis": "junk"})


class TestSolventRules:
    def test_solvent_requires_solvent_model(self):
        with pytest.raises(ValueError, match="missing solvent-model"):
            build(**{"solvent": "water"})

    def test_solvent_model_requires_solvent(self):
        with pytest.raises(ValueError, match="missing solvent"):
            build(**{"solvent-model": "SMD"})

    def test_no_solvent_defaults(self):
        document = build()
        assert document["solvent"] == "None"
        assert document["solvent_model"] == "CPCM"
        assert document["use_solvent"] is False

    def test_with_solvent(self):
        document = build(solvent="water", **{"solvent-model": "SMD"})
        assert document["solvent"] == "water"
        assert document["solvent_model"] == "SMD"
        assert document["use_solvent"] is True

    def test_solvent_none_is_an_error(self):
        with pytest.raises(ValueError, match="omit solvent"):
            build(solvent="None", **{"solvent-model": "CPCM"})


class TestExcitedStatesRules:
    def test_states_and_focus_states(self):
        document = build(states=5, **{"focus-states": 3})
        assert document["states"] == 5
        assert document["focus_state"] == 3
        assert document["excited_states"] is True
        assert document["compute_properties"] is False

    def test_focus_states_requires_states(self):
        with pytest.raises(ValueError, match="focus-states requires states > 0"):
            build(**{"focus-states": 3})

    def test_focus_states_within_states(self):
        with pytest.raises(ValueError, match="focus-states 9 is not among"):
            build(states=5, **{"focus-states": 9})

    def test_negative_states(self):
        with pytest.raises(ValueError, match="states must be >= 0"):
            build(states=-1)

    def test_active_space_requires_active_electrons(self):
        with pytest.raises(ValueError, match="active-electrons"):
            build(method="CASSCF", states=2, **{"focus-states": 1})

    def test_frequencies_incompatible_with_states(self):
        with pytest.raises(ValueError, match="frequencies with states"):
            build(states=2, frequencies=True)

    def test_hyperpol_incompatible_with_states(self):
        with pytest.raises(ValueError, match="hyperpol with states"):
            build(states=2, hyperpol=True, **{"hyperpol-frequency-nm": 532})


class TestElPropRules:
    def test_dipole_sets_compute_properties(self):
        document = build(dipole=True)
        assert document["Dipole"] is True
        assert document["compute_properties"] is True

    def test_hyperpol_requires_frequency(self):
        with pytest.raises(ValueError, match="missing hyperpol-frequency-nm"):
            build(hyperpol=True)

    def test_frequency_requires_hyperpol(self):
        with pytest.raises(ValueError, match="requires hyperpol true"):
            build(**{"hyperpol-frequency-nm": 532})

    def test_hyperpol_frequency(self):
        document = build(hyperpol=True, **{"hyperpol-frequency-nm": 532})
        assert document["Hyperpol"] is True
        assert document["HyperpolFrequencynm"] == 532.0
        assert document["compute_properties"] is True


class TestFrozenAtoms:
    def test_constraints_are_emitted(self):
        document = build(**{"frozen-atoms": [0, 2]})
        assert document["molecule"]["properties"]["constraints"] == [
            {"type": "frozen", "index": 0},
            {"type": "frozen", "index": 2},
        ]

    def test_out_of_range_index(self):
        with pytest.raises(ValueError, match="outside the 3 atoms"):
            build(**{"frozen-atoms": [3]})

    def test_negative_index(self):
        with pytest.raises(ValueError, match="outside the 3 atoms"):
            build(**{"frozen-atoms": [-1]})

    def test_duplicate_index(self):
        with pytest.raises(ValueError, match="duplicated"):
            build(**{"frozen-atoms": [1, 1]})

    def test_non_integer_index(self):
        with pytest.raises(ValueError, match="frozen-atoms must be a list"):
            build(**{"frozen-atoms": ["O"]})


class TestXyzValidation:
    def test_empty_xyz(self):
        with pytest.raises(ValueError, match="empty"):
            build_legacy_qm_input(water_settings(), "")

    def test_non_integer_atom_count(self):
        with pytest.raises(ValueError, match="not an integer"):
            build_legacy_qm_input(water_settings(), "water\ncomment\nO 0 0 0\n")

    def test_atom_count_mismatch(self):
        xyz = (
            "4\nwater\nO 0.0 0.0 0.117\nH 0.0 0.755 -0.471\nH 0.0 -0.755 -0.471\n"
        )
        with pytest.raises(ValueError, match="declares 4 atoms"):
            build_legacy_qm_input(water_settings(), xyz)

    def test_zero_atoms(self):
        with pytest.raises(ValueError, match="no atoms"):
            build_legacy_qm_input(water_settings(), "0\ncomment\n")


