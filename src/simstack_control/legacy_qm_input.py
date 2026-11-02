"""Build submission documents for the legacy ``orca_jinja`` node.

The legacy simstack-model environment (this branch of simstack-control pins
``simstack==v2.0.1.post1`` and ``molecular_qm_models==72f8dcb``) validates
its qm_input against :class:`molecular_qm_models.qm_input.QMInput` — the
document schema that is stored today in the production DB.  ``main`` instead
uses the new ``OrcaQMInput`` from ``molecular_qm_orca.models``, which does not
exist at the pinned legacy revision.

This module maps a *short* settings JSON object plus an XYZ geometry onto that
legacy document and validates it exactly like ``submit_cli.submit_inputs``
does (``QMInput.from_dict`` → ``model_validate``), so agents can submit the
legacy ``orca_jinja`` node without constructing the full document by hand.
"""

from collections.abc import Mapping
from typing import Any

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
    QMInput,
    SCFAccuracy,
    SolventModel,
)

# Required short-settings keys (same contract as the old submit_orca example).
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

# Short key -> legacy QMInput boolean field.
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

# Short key -> (legacy QMInput field, enum class).
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
    "frozen-atoms",
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
    """Resolve a short-settings value to the canonical enum string."""
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{key} must be a non-empty string")
    text = value.strip().lower()
    for item in enum_cls:
        if item.value.lower() == text or item.name.lower() == text:
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


def build_legacy_qm_input(parameters: Mapping[str, Any], xyz_text: str) -> dict:
    """Map a short settings object and XYZ geometry onto the legacy QMInput.

    The returned document mirrors the de-facto shape of the documents stored
    in the production DB for the ``orca_jinja`` node (all fields explicit,
    embedded ``field_name`` attributes, ``Functional`` with its embedded
    ``DispersionCorrection``).  It is validated via ``QMInput.from_dict`` —
    the exact code path ``submit_cli.submit_inputs`` uses.
    """
    if not isinstance(parameters, Mapping):
        raise ValueError("orca_jinja.json must be a JSON object")
    settings = dict(parameters)
    if "molecule" in settings or "qm_input" in settings:
        raise ValueError(
            "orca_jinja.json must not contain a molecule; pass the geometry as molecule.xyz"
        )
    missing = [key for key in REQUIRED_KEYS if key not in settings]
    unknown = sorted(key for key in settings if key not in KNOWN_KEYS)
    if missing or unknown:
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        raise ValueError("orca_jinja.json " + "; ".join(details))
    nulls = [key for key, value in settings.items() if value is None]
    if nulls:
        raise ValueError(f"{', '.join(nulls)} must not be null")

    basis_set = enum_value(BasisSetEnum, settings["basis-set"], "basis-set")
    aux_basis = enum_value(AuxBasisEnum, settings["aux-basis"], "aux-basis")
    functional = enum_value(FunctionalEnum, settings["functional"], "functional")
    dispersion = enum_value(
        DispersionCorrectionEnum, settings["dispersion"], "dispersion"
    )
    method = enum_value(QMMethod, settings["method"], "method")
    charge = integer_value("charge", settings["charge"])
    multiplicity = integer_value("multiplicity", settings["multiplicity"])
    if multiplicity < 1:
        raise ValueError("multiplicity must be >= 1")
    optimization = boolean_value("optimization", settings["optimization"])
    if optimization and "optimization-accuracy" not in settings:
        raise ValueError("orca_jinja.json is missing optimization-accuracy")

    booleans = {}
    for key, field in BOOL_FIELDS.items():
        if key in settings:
            booleans[field] = boolean_value(key, settings[key])
    open_shell_calculation = booleans.get("open_shell_calculation", False)
    frequencies = booleans.get("frequencies", False)
    tolerate_failure = booleans.get("tolerate_failure", False)
    dipole = booleans.get("Dipole", False)
    quadrupole = booleans.get("Quadrupole", False)
    polar = booleans.get("Polar", False)
    hyperpol = booleans.get("Hyperpol", False)
    polar_velocity = booleans.get("PolarVelocity", False)
    polar_dip_quad = booleans.get("PolarDipQuad", False)
    polar_quad_quad = booleans.get("PolarQuadQuad", False)

    enums = {}
    for key, (field, enum_cls) in ENUM_FIELDS.items():
        if key in settings:
            enums[field] = enum_value(enum_cls, settings[key], key)
    scf_accuracy = enums.get("scf_accuracy", SCFAccuracy.Medium.value)
    optimization_accuracy = enums.get(
        "optimization_accuracy", OptimizationAccuracy.Medium.value
    )
    grid_type = enums.get("grid_type", GridType.Grid2.value)
    solvent_model = enums.get("solvent_model", SolventModel.CPCM.value)

    ints = {}
    for key, field in INT_FIELDS.items():
        if key in settings:
            ints[field] = integer_value(key, settings[key])
    print_level = ints.get("print_level", 1)
    if not 0 <= print_level <= 5:
        raise ValueError("print-level must be between 0 and 5")
    max_scf_iterations = ints.get("max_scf_iterations", 100)
    max_optimization_iterations = ints.get("max_optimization_iterations", 100)
    if max_scf_iterations < 1:
        raise ValueError("max-scf-iterations must be >= 1")
    if max_optimization_iterations < 1:
        raise ValueError("max-optimization-iterations must be >= 1")
    active_electrons = ints.get("active_electrons", 0)
    active_orbitals = ints.get("active_orbitals", 0)

    floats = {}
    for key, field in FLOAT_FIELDS.items():
        if key in settings:
            floats[field] = number_value(key, settings[key])
    grid_spacing = floats.get("grid_spacing", 0.2)

    states = 0
    if "states" in settings:
        states = integer_value("states", settings["states"])
        if states < 0:
            raise ValueError("states must be >= 0")
    focus_state = 1
    if "focus-states" in settings:
        if states <= 0:
            raise ValueError("focus-states requires states > 0")
        focus_state = integer_value("focus-states", settings["focus-states"])
        if focus_state < 1:
            raise ValueError("focus-states must be >= 1")
        if focus_state > states:
            raise ValueError(
                f"focus-states {focus_state} is not among states 1..{states}"
            )
    if method in ACTIVE_SPACE_METHODS and states > 0:
        missing_active = [
            key
            for key in ("active-electrons", "active-orbitals")
            if key not in settings
        ]
        if missing_active:
            raise ValueError("orca_jinja.json is missing " + ", ".join(missing_active))
    for key in ("active-electrons", "active-orbitals"):
        if key in settings:
            active = integer_value(key, settings[key])
            if active < 0:
                raise ValueError(f"{key} must be >= 0")

    has_solvent = "solvent" in settings
    has_solvent_model = "solvent-model" in settings
    if has_solvent != has_solvent_model:
        missing_solvent = "solvent-model" if has_solvent else "solvent"
        raise ValueError(f"orca_jinja.json is missing {missing_solvent}")
    if has_solvent:
        solvent = settings["solvent"]
        if not isinstance(solvent, str) or solvent.strip() == "":
            raise ValueError("solvent must be a non-empty string")
        if solvent.strip().lower() == "none":
            raise ValueError("omit solvent to run without a solvent")
        use_solvent = True
    else:
        solvent = "None"
        use_solvent = False

    has_frequency = "hyperpol-frequency-nm" in settings
    if hyperpol is True and not has_frequency:
        raise ValueError("orca_jinja.json is missing hyperpol-frequency-nm")
    if hyperpol is not True and has_frequency:
        raise ValueError("hyperpol-frequency-nm requires hyperpol true")
    if has_frequency:
        hyperpol_frequency_nm = number_value(
            "hyperpol-frequency-nm", settings["hyperpol-frequency-nm"]
        )
        if hyperpol_frequency_nm < 0:
            raise ValueError("hyperpol-frequency-nm must be >= 0")
    else:
        hyperpol_frequency_nm = 0.0

    if "first-line" in settings and not isinstance(settings["first-line"], str):
        raise ValueError("first-line must be a string")
    first_line = settings.get("first-line", "")
    if "blocks" in settings:
        blocks = settings["blocks"]
        if not isinstance(blocks, list) or any(
            not isinstance(item, str) for item in blocks
        ):
            raise ValueError("blocks must be a list of strings")
    else:
        blocks = []

    # Legacy QMInput sanity checks (mirrors validate_calculation_options).
    if frequencies and states > 0:
        raise ValueError("frequencies with states > 0 is not supported; set states=0")
    if hyperpol and states > 0:
        raise ValueError("hyperpol with states > 0 is not supported; set states=0")

    compute_properties = any(
        (
            dipole,
            quadrupole,
            polar,
            hyperpol,
            polar_velocity,
            polar_dip_quad,
            polar_quad_quad,
        )
    ) or hyperpol_frequency_nm != 0.0

    molecule = _molecule_document(xyz_text)

    frozen = _frozen_indices(settings.get("frozen-atoms"), len(molecule["atoms"]))
    if frozen:
        properties = dict(molecule.get("properties") or {})
        properties["constraints"] = [
            {"type": "frozen", "index": index} for index in frozen
        ]
        molecule["properties"] = properties

    qm_input = {
        "field_name": "QMInput",
        "molecule": molecule,
        "charge": charge,
        "multiplicity": multiplicity,
        "open_shell_calculation": open_shell_calculation,
        "basis_set": {
            "field_name": "BasisSet",
            "basis_set": basis_set,
            "aux_basis": {
                "field_name": "AuxBasis",
                "aux_basis": aux_basis,
            },
        },
        "functional": {
            "field_name": "Functional",
            "functional": functional,
            "dispersion_correction": {
                "field_name": "DispersionCorrection",
                "value": dispersion,
            },
        },
        "method": method,
        "gradients": booleans.get("gradients", False),
        "optimization": optimization,
        "frequencies": frequencies,
        "solvent": solvent,
        "solvent_model": solvent_model,
        "use_solvent": use_solvent,
        "print_level": print_level,
        "scf_accuracy": scf_accuracy,
        "optimization_accuracy": optimization_accuracy,
        "grid_type": grid_type,
        "grid_spacing": grid_spacing,
        "max_scf_iterations": max_scf_iterations,
        "max_optimization_iterations": max_optimization_iterations,
        "first_line": first_line,
        "blocks": blocks,
        "Dipole": dipole,
        "Quadrupole": quadrupole,
        "Polar": polar,
        "Hyperpol": hyperpol,
        "HyperpolFrequencynm": hyperpol_frequency_nm,
        "PolarVelocity": polar_velocity,
        "PolarDipQuad": polar_dip_quad,
        "PolarQuadQuad": polar_quad_quad,
        "states": states,
        "focus_state": focus_state,
        "active_electrons": active_electrons,
        "active_orbitals": active_orbitals,
        "restart_files": {"elements": []},
        "tolerate_failure": tolerate_failure,
        "excited_states": states > 0,
        "compute_properties": compute_properties,
        "non_standard_inputs": False,
        "non_standard_parameters": False,
    }

    _validate_legacy_qm_input(qm_input)
    return qm_input


def _validate_legacy_qm_input(qm_input: dict) -> None:
    """Validate through the same code path submit_cli uses for legacy models."""
    if hasattr(QMInput, "from_dict"):
        try:
            QMInput.from_dict(qm_input)
        except (ValidationError, ValueError) as exc:
            raise ValueError(
                f"orca_jinja.json produced an invalid QMInput: {exc}"
            ) from exc
    else:
        try:
            QMInput.model_validate(qm_input)
        except (ValidationError, ValueError) as exc:
            raise ValueError(
                f"orca_jinja.json produced an invalid QMInput: {exc}"
            ) from exc


def _molecule_document(xyz_text: str) -> dict:
    """Parse an XYZ file into the embedded Molecule document dict."""
    if not isinstance(xyz_text, str):
        raise ValueError("molecule.xyz must be text")
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
    return {
        "field_name": "Molecule",
        "atoms": [
            {
                "field_name": "Atom",
                "element": atom.element,
                "x": atom.x,
                "y": atom.y,
                "z": atom.z,
                "properties": {},
            }
            for atom in molecule.atoms
        ],
        "properties": {},
        "smiles": None,
        "formula": None,
    }


def _frozen_indices(value, n_atoms: int):
    """Normalize the ``frozen-atoms`` short key (0-based atom indices)."""
    if value is None:
        return []
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in value
    ):
        raise ValueError("frozen-atoms must be a list of 0-based atom indices")
    seen = []
    for index in value:
        if isinstance(index, bool) or not isinstance(index, int):
            raise ValueError("frozen-atoms must be a list of 0-based atom indices")
        if index < 0 or index >= n_atoms:
            raise ValueError(
                f"frozen-atoms index {index} is outside the {n_atoms} atoms"
            )
        if index in seen:
            raise ValueError(f"frozen-atoms index {index} is duplicated")
        seen.append(index)
    return seen


def build_orca_jinja_submit_input(
    parameters: Mapping[str, Any], xyz_text: str
) -> dict:
    """Return the full ``simstack_submit --node-name orca_jinja`` document."""
    return {"qm_input": build_legacy_qm_input(parameters, xyz_text)}


