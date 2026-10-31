import pytest

from simstack_control.inputs import require_input_document


def test_accepts_exact_input_names():
    payload = require_input_document({"molecule": {"atoms": []}, "basis": {"name": "sto-3g"}}, ["molecule", "basis"])
    assert payload["basis"]["name"] == "sto-3g"


def test_rejects_missing_and_extra_keys():
    with pytest.raises(ValueError, match="missing"):
        require_input_document({"molecule": {}}, ["molecule", "basis"])
    with pytest.raises(ValueError, match="unexpected"):
        require_input_document({"molecule": {}, "extra": {}}, ["molecule"])


def test_rejects_non_object_input():
    with pytest.raises(ValueError, match="must be a JSON object"):
        require_input_document({"molecule": [1, 2]}, ["molecule"])
    with pytest.raises(ValueError, match="inputs.json must be a JSON object"):
        require_input_document([{"molecule": {}}], ["molecule"])
