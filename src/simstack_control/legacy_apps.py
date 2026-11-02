"""Client-side helpers to import the legacy simstack-model application tree.

``submit_cli.submit_inputs`` imports the registered node function
``applications.electronic_structure.orca.orca.orca_jinja`` from the
simstack-model checkout via ``simstack.util.importer.import_function``.
That package unconditionally imports ``molecular_qm_util`` (an
openbabel-backed helper used by the runner):

    applications/electronic_structure/__init__.py
        from molecular_qm_util import compute_smiles, ...

The simstack-control client must not install openbabel, so before the
applications tree is imported we guarantee that ``import molecular_qm_util``
succeeds: the real package wins when it is importable (e.g. on a runner
host), otherwise a minimal stand-in module provides the five re-exported
names — they are runner-side services and are never called client-side.
"""

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType

LEGACY_MODEL_REPO_NAME = "simstack-model"

# Re-exported names imported unconditionally by the applications tree.
_MOLECULAR_QM_UTIL_NAMES = (
    "compute_smiles",
    "smiles_to_molecule",
    "compute_iupac_name",
    "molecule_to_pymatgen",
    "pymatgen_to_molecule",
)


def ensure_molecular_qm_util() -> str:
    """Make ``import molecular_qm_util`` succeed.

    Returns ``"real"`` when the package is installed and importable and
    ``"stub"`` when a client-side stand-in was registered.
    """
    if "molecular_qm_util" in sys.modules:
        return "real"
    try:
        importlib.import_module("molecular_qm_util")
    except ImportError:
        _install_molecular_qm_util_stub()
        return "stub"
    return "real"


def _install_molecular_qm_util_stub() -> None:
    def unavailable(*_args, **_kwargs):
        raise RuntimeError(
            "molecular_qm_util is a runner-side service and is not installed "
            "in the simstack-control client environment"
        )

    module = ModuleType("molecular_qm_util")
    module.__doc__ = (
        "Client-side stand-in for the runner-only molecular_qm_util package "
        "(openbabel-backed). Its functions raise RuntimeError when called."
    )
    for name in _MOLECULAR_QM_UTIL_NAMES:
        setattr(module, name, unavailable)
    sys.modules["molecular_qm_util"] = module


def _sibling_model_root() -> str | None:
    sibling = Path(__file__).resolve().parents[3] / LEGACY_MODEL_REPO_NAME
    return str(sibling) if sibling.is_dir() else None


def resolve_model_root() -> str:
    """Locate the simstack-model checkout with the legacy applications tree."""
    configured = os.environ.get("SIMSTACK_MODEL_DIR")
    if configured:
        return configured
    sibling = _sibling_model_root()
    if sibling:
        return sibling
    raise RuntimeError(
        "Could not locate the simstack-model checkout. Set SIMSTACK_MODEL_DIR "
        f"or place it next to this repository as "
        f"{Path(__file__).resolve().parents[3] / LEGACY_MODEL_REPO_NAME}."
    )


def ensure_pymatgen() -> str:
    """Make the pymatgen names used by the orca application importable.

    ``applications/electronic_structure/orca/pyorca.py`` imports
    ``Spin``, ``Element`` and ``Molecule`` (pymatgen) at module level, but
    uses them only inside methods.  The client needs the module import to
    succeed for ``inspect.signature`` on the node function, so a small
    stand-in provides the import-time surface when pymatgen is not
    installed.  Returns ``"real"`` or ``"stub"``.
    """
    if "pymatgen" in sys.modules:
        return "real"
    try:
        importlib.import_module("pymatgen")
    except ImportError:
        _install_pymatgen_stub()
        return "stub"
    return "real"


def _install_pymatgen_stub() -> None:
    pymatgen = ModuleType("pymatgen")
    core = ModuleType("pymatgen.core")
    electronic_structure = ModuleType("pymatgen.electronic_structure")
    es_core = ModuleType("pymatgen.electronic_structure.core")

    class Spin:
        up = 1
        down = -1

    class Element:
        def __init__(self, symbol):
            self.symbol = str(symbol)

        def __repr__(self):
            return f"Element('{self.symbol}')"

        @classmethod
        def from_symbol(cls, symbol):
            return cls(symbol)

    class PymatgenMolecule:
        def __init__(self, *args, **kwargs):
            pass

    es_core.Spin = Spin  # type: ignore[attr-defined]
    core.Element = Element  # type: ignore[attr-defined]
    core.Molecule = PymatgenMolecule  # type: ignore[attr-defined]
    pymatgen.core = core  # type: ignore[attr-defined]
    pymatgen.electronic_structure = electronic_structure  # type: ignore[attr-defined]
    electronic_structure.core = es_core  # type: ignore[attr-defined]

    sys.modules["pymatgen"] = pymatgen
    sys.modules["pymatgen.core"] = core
    sys.modules["pymatgen.electronic_structure"] = electronic_structure
    sys.modules["pymatgen.electronic_structure.core"] = es_core


def import_legacy_orca_node():
    """Import and return ``applications.electronic_structure.orca.orca``.

    Registers the ``molecular_qm_util``/``pymatgen`` stand-ins when needed
    and prepends the simstack-model checkout to ``sys.path`` so
    ``applications`` resolves.
    """
    ensure_molecular_qm_util()
    ensure_pymatgen()
    model_root = resolve_model_root()
    if model_root not in sys.path:
        sys.path.insert(0, model_root)
    try:
        return importlib.import_module(
            "applications.electronic_structure.orca.orca"
        )
    except ImportError as exc:
        raise RuntimeError(
            "Could not import the legacy orca application tree. Point "
            "SIMSTACK_MODEL_DIR at the simstack-model checkout: "
            f"{exc}"
        ) from exc
