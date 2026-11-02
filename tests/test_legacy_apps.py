"""Tests for the client-side legacy applications helpers.

``legacy_apps`` makes the runner-side ``applications`` import chain work on
the client without installing openbabel/pymatgen/molecular_qm_util.  These
tests run without a database and without those heavy packages.
"""

import sys

import pytest

from simstack_control import legacy_apps

WATER_XYZ = (
    "3\nwater\nO 0.0 0.0 0.117\nH 0.0 0.755 -0.471\nH 0.0 -0.755 -0.471\n"
)


class TestMolecularQmUtilFallback:
    def test_fallback_provides_runner_names(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "molecular_qm_util", raising=False)
        result = legacy_apps.ensure_molecular_qm_util()
        import molecular_qm_util

        for name in legacy_apps._MOLECULAR_QM_UTIL_NAMES:
            assert hasattr(molecular_qm_util, name)
        if result == "stub":
            with pytest.raises(RuntimeError, match="runner-side service"):
                molecular_qm_util.compute_smiles("C")

    def test_second_call_keeps_registered_module(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "molecular_qm_util", raising=False)
        assert legacy_apps.ensure_molecular_qm_util() in ("real", "stub")
        got = legacy_apps.ensure_molecular_qm_util()
        assert got in ("real", "stub")
        assert "molecular_qm_util" in sys.modules


class TestPymatgenFallback:
    def test_import_time_surface_available(self, monkeypatch):
        for name in (
            "pymatgen",
            "pymatgen.core",
            "pymatgen.electronic_structure",
            "pymatgen.electronic_structure.core",
        ):
            monkeypatch.delitem(sys.modules, name, raising=False)

        result = legacy_apps.ensure_pymatgen()
        from pymatgen.core import Element, Molecule as PymatgenMolecule
        from pymatgen.electronic_structure.core import Spin

        assert result in ("real", "stub")
        assert Spin.up != Spin.down
        if result == "stub":
            assert str(Element.from_symbol("O")) == "Element('O')"
            PymatgenMolecule()


class TestImportLegacyOrcaNode:
    def test_imports_orca_jinja_from_model_dir(self, monkeypatch):
        import inspect
        import pathlib

        repo = pathlib.Path(__file__).resolve().parents[1].with_name("simstack-model")
        assert (repo / "applications").is_dir()
        monkeypatch.setenv("SIMSTACK_MODEL_DIR", str(repo))

        module = legacy_apps.import_legacy_orca_node()
        assert module.orca_jinja.__name__ == "orca_jinja"
        assert list(inspect.signature(module.orca_jinja).parameters) == [
            "qm_input",
            "kwargs",
        ]

    def test_missing_model_dir_raises(self, monkeypatch):
        monkeypatch.delenv("SIMSTACK_MODEL_DIR", raising=False)
        monkeypatch.setattr(legacy_apps, "_sibling_model_root", lambda: None)
        with pytest.raises(RuntimeError, match="SIMSTACK_MODEL_DIR"):
            legacy_apps.resolve_model_root()
