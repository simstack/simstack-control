from simstack_control.inspect_cli import (
    _file_stack_field_names,
    _referenced_model_fields,
)


def test_orca_input_resolves_molecule_and_skips_file_stacks():
    from molecular_qm_models.qm_input import QMInput

    referenced = _referenced_model_fields(QMInput)
    assert referenced["molecule"].__name__ == "Molecule"
    assert "restart_files" in _file_stack_field_names(QMInput)
    assert "restart_files" not in referenced


def test_qm_result_skips_the_file_list():
    from molecular_qm_models.qm_result import QMResult

    assert "files" in _file_stack_field_names(QMResult)
    assert "files" not in _referenced_model_fields(QMResult)
    assert "final_structure" in _referenced_model_fields(QMResult)
