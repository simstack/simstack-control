"""Submit the ORCA node from a short parameters file and an XYZ geometry.

    python examples/submit_orca.py --parameters orca.json --resource jusuf molecule.xyz

The parameters file uses the calculation settings from ``orca_input.json``
in the repository root, without a molecule. Required keys are ``basis-set``,
``aux-basis``, ``functional``, ``dispersion``, ``method``, ``charge``,
``multiplicity``, and ``optimization``. ``states`` and ``focus-states`` are
optional; ``focus-states`` is required when ``states`` is greater than 0.
The XYZ file supplies the molecule. The script builds the ``qm_input``
document ``simstack_submit --node-name orca`` expects and submits it.
"""

import argparse
import asyncio
import copy
import sys
from pathlib import Path

from pydantic import ValidationError

from molecular_qm_models.auxiliary_basis import AuxBasisEnum
from molecular_qm_models.basis_set import BasisSetEnum
from molecular_qm_models.density_functional import FunctionalEnum
from molecular_qm_models.dispersion_correction import DispersionCorrectionEnum
from molecular_qm_models.molecule import Molecule
from molecular_qm_models.qm_input import (
    GridType,
    OptimizationAccuracy,
    QMMethod,
    SCFAccuracy,
    SolventModel,
)
from molecular_qm_orca.models.orca_qm_input import OrcaQMInput
from simstack_control.jsonutil import load_json_file

REQUIRED_KEYS = (
    "basis-set",
    "aux-basis",
    "functional",
    "dispersion",
    "method",
    "charge",
    "multiplicity",
    "optimization",
)

BOOL_FIELDS = {
    "open-shell": "open_shell_calculation",
    "frequencies": "frequencies",
    "gradients": "gradients",
    "tolerate-failure": "tolerate_failure",
    "dipole": "Dipole",
    "quadrupole": "Quadrupole",
    "polar": "Polar",
    "hyperpol": "Hyperpol",
    "polar-velocity": "PolarVelocity",
    "polar-dip-quad": "PolarDipQuad",
    "polar-quad-quad": "PolarQuadQuad",
}

ENUM_FIELDS = {
    "scf-accuracy": ("scf_accuracy", SCFAccuracy),
    "optimization-accuracy": ("optimization_accuracy", OptimizationAccuracy),
    "grid-type": ("grid_type", GridType),
    "solvent-model": ("solvent_model", SolventModel),
}

INT_FIELDS = {
    "print-level": "print_level",
    "max-scf-iterations": "max_scf_iterations",
    "max-optimization-iterations": "max_optimization_iterations",
}

FLOAT_FIELDS = {
    "grid-spacing": "grid_spacing",
}

SPECIAL_KEYS = (
    "states",
    "focus-states",
    "active-electrons",
    "active-orbitals",
    "solvent",
    "hyperpol-frequency-nm",
    "first-line",
    "blocks",
)

ACTIVE_SPACE_METHODS = {"CASSCF", "DFTMRCI"}

KNOWN_KEYS = (
    set(REQUIRED_KEYS)
    | set(BOOL_FIELDS)
    | set(ENUM_FIELDS)
    | set(INT_FIELDS)
    | set(FLOAT_FIELDS)
    | set(SPECIAL_KEYS)
)


def enum_value(enum_cls, value, key):
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{key} must be a non-empty string")
    text = value.strip()
    for item in enum_cls:
        if item.value.lower() == text.lower() or item.name.lower() == text.lower():
            return item.value
    allowed = ", ".join(item.value for item in enum_cls)
    raise ValueError(f"{key} {value!r} is not one of: {allowed}")


def integer_value(key, value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def boolean_value(key, value):
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be true or false")
    return value


def number_value(key, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    return float(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="submit_orca",
        description=(
            "Build the orca qm_input document from a short parameters file "
            "and an XYZ geometry, then submit node orca."
        ),
    )
    parser.add_argument(
        "--parameters",
        required=True,
        help="Short ORCA settings JSON. Must not contain a molecule.",
    )
    parser.add_argument("--resource", required=True, help="Execution resource.")
    parser.add_argument("--custom-name", help="Optional display name.")
    parser.add_argument("--category", help="Optional category.")
    parser.add_argument("molecule", help="XYZ file for the molecule.")
    return parser


def build_orca_submit_input(parameters, xyz_text: str) -> dict:
    """Map a short settings object and XYZ text onto the orca node inputs."""
    if not isinstance(parameters, dict):
        raise ValueError("orca.json must be a JSON object")
    if "molecule" in parameters or "qm_input" in parameters:
        raise ValueError(
            "orca.json must not contain a molecule; pass the geometry as molecule.xyz"
        )
    missing = [key for key in REQUIRED_KEYS if key not in parameters]
    unknown = sorted(key for key in parameters if key not in KNOWN_KEYS)
    if missing or unknown:
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        raise ValueError("orca.json " + "; ".join(details))
    nulls = [key for key, value in parameters.items() if value is None]
    if nulls:
        raise ValueError(f"{', '.join(nulls)} must not be null")

    basis_set = enum_value(BasisSetEnum, parameters["basis-set"], "basis-set")
    aux_basis = enum_value(AuxBasisEnum, parameters["aux-basis"], "aux-basis")
    functional = enum_value(FunctionalEnum, parameters["functional"], "functional")
    dispersion = enum_value(
        DispersionCorrectionEnum, parameters["dispersion"], "dispersion"
    )
    method = enum_value(QMMethod, parameters["method"], "method")
    charge = integer_value("charge", parameters["charge"])
    multiplicity = integer_value("multiplicity", parameters["multiplicity"])
    if multiplicity < 1:
        raise ValueError("multiplicity must be >= 1")
    optimization = boolean_value("optimization", parameters["optimization"])
    if optimization and "optimization-accuracy" not in parameters:
        raise ValueError("orca.json is missing optimization-accuracy")

    states = None
    if "states" in parameters:
        states = integer_value("states", parameters["states"])
        if states < 0:
            raise ValueError("states must be >= 0")
    if "focus-states" in parameters:
        if states is None or states <= 0:
            raise ValueError("focus-states requires states > 0")
        focus_state = integer_value("focus-states", parameters["focus-states"])
        if focus_state < 1 or focus_state > states:
            raise ValueError(f"focus-states must be between 1 and {states}")
    elif states is not None and states > 0:
        raise ValueError("orca.json is missing focus-states")

    for key in ("active-electrons", "active-orbitals"):
        if key in parameters and (states is None or states <= 0):
            raise ValueError(f"{key} requires states > 0")
    if method in ACTIVE_SPACE_METHODS and states is not None and states > 0:
        missing_active = [
            key
            for key in ("active-electrons", "active-orbitals")
            if key not in parameters
        ]
        if missing_active:
            raise ValueError("orca.json is missing " + ", ".join(missing_active))
    for key in ("active-electrons", "active-orbitals"):
        if key in parameters:
            active = integer_value(key, parameters[key])
            if active < 0:
                raise ValueError(f"{key} must be >= 0")

    has_solvent = "solvent" in parameters
    has_solvent_model = "solvent-model" in parameters
    if has_solvent != has_solvent_model:
        missing_solvent = "solvent-model" if has_solvent else "solvent"
        raise ValueError(f"orca.json is missing {missing_solvent}")
    if has_solvent:
        solvent = parameters["solvent"]
        if not isinstance(solvent, str) or solvent.strip() == "":
            raise ValueError("solvent must be a non-empty string")
        if solvent.strip().lower() == "none":
            raise ValueError("omit solvent to run without a solvent")

    hyperpol = parameters["hyperpol"] if "hyperpol" in parameters else None
    has_frequency = "hyperpol-frequency-nm" in parameters
    if hyperpol is True and not has_frequency:
        raise ValueError("orca.json is missing hyperpol-frequency-nm")
    if hyperpol is not True and has_frequency:
        raise ValueError("hyperpol-frequency-nm requires hyperpol true")
    if has_frequency:
        frequency = number_value(
            "hyperpol-frequency-nm", parameters["hyperpol-frequency-nm"]
        )
        if frequency < 0:
            raise ValueError("hyperpol-frequency-nm must be >= 0")

    if "first-line" in parameters and not isinstance(parameters["first-line"], str):
        raise ValueError("first-line must be a string")
    if "blocks" in parameters:
        blocks = parameters["blocks"]
        if not isinstance(blocks, list) or any(not isinstance(item, str) for item in blocks):
            raise ValueError("blocks must be a list of strings")

    lines = xyz_text.splitlines()
    if not lines or lines[0].strip() == "":
        raise ValueError("molecule.xyz is empty")
    try:
        declared = int(lines[0].strip())
    except ValueError as exc:
        raise ValueError(
            f"molecule.xyz atom count is not an integer: {lines[0]!r}"
        ) from exc
    molecule = Molecule.from_xyz(xyz_text)
    if len(molecule.atoms) != declared:
        raise ValueError(
            f"molecule.xyz declares {declared} atoms but {len(molecule.atoms)} could be read"
        )
    if declared == 0:
        raise ValueError("molecule.xyz contains no atoms")

    qm_input = {
        "field_name": "OrcaQMInput",
        "method": method,
        "charge": charge,
        "multiplicity": multiplicity,
        "optimization": optimization,
        "functional": {
            "field_name": "OrcaFunctional",
            "functional": functional,
        },
        "dispersion_correction": {
            "field_name": "DispersionCorrection",
            "value": dispersion,
        },
        "basis_set": {
            "field_name": "BasisSet",
            "basis_set": basis_set,
            "aux_basis": {
                "field_name": "AuxBasis",
                "aux_basis": aux_basis,
            },
        },
    }
    if states is not None:
        qm_input["states"] = states
    if "focus-states" in parameters:
        qm_input["focus_state"] = focus_state
    for key, field in (
        ("active-electrons", "active_electrons"),
        ("active-orbitals", "active_orbitals"),
    ):
        if key in parameters:
            qm_input[field] = parameters[key]
    if has_solvent:
        qm_input["solvent"] = parameters["solvent"].strip()
    if has_frequency:
        qm_input["HyperpolFrequencynm"] = frequency
    if "first-line" in parameters:
        qm_input["first_line"] = parameters["first-line"]
    if "blocks" in parameters:
        qm_input["blocks"] = parameters["blocks"]
    for key, field in BOOL_FIELDS.items():
        if key in parameters:
            qm_input[field] = boolean_value(key, parameters[key])
    for key, (field, enum_cls) in ENUM_FIELDS.items():
        if key in parameters:
            qm_input[field] = enum_value(enum_cls, parameters[key], key)
    for key, field in INT_FIELDS.items():
        if key in parameters:
            value = integer_value(key, parameters[key])
            if key == "print-level" and not 0 <= value <= 4:
                raise ValueError("print-level must be between 0 and 4")
            if key != "print-level" and value < 1:
                raise ValueError(f"{key} must be >= 1")
            qm_input[field] = value
    for key, field in FLOAT_FIELDS.items():
        if key in parameters:
            value = number_value(key, parameters[key])
            if value <= 0:
                raise ValueError(f"{key} must be > 0")
            qm_input[field] = value
    qm_input["molecule"] = {
        "field_name": "Molecule",
        "atoms": [
            {
                "field_name": "Atom",
                "element": atom.element,
                "x": atom.x,
                "y": atom.y,
                "z": atom.z,
            }
            for atom in molecule.atoms
        ],
    }
    try:
        OrcaQMInput.model_validate(copy.deepcopy(qm_input))
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    return {"qm_input": qm_input}


async def _main(args) -> None:
    parameters = load_json_file(args.parameters)
    molecule_path = Path(args.molecule)
    if molecule_path.suffix.lower() != ".xyz":
        raise ValueError(f"{args.molecule} must be an .xyz file")
    try:
        xyz_text = molecule_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read {args.molecule}: {exc}") from exc
    document = build_orca_submit_input(parameters, xyz_text)
    from simstack_control.submit_cli import submit_inputs

    print(
        await submit_inputs(
            "orca",
            args.resource,
            document,
            custom_name=args.custom_name,
            category=args.category,
        )
    )


def main() -> None:
    args = build_parser().parse_args()
    try:
        asyncio.run(_main(args))
    except (ValueError, LookupError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
