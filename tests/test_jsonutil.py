from datetime import datetime, timezone

import pytest
from bson import ObjectId

from simstack_control.jsonutil import to_jsonable


def test_converts_object_ids_and_datetimes():
    instant = datetime(2026, 10, 31, tzinfo=timezone.utc)
    identifier = ObjectId("0123456789abcdef01234567")
    assert to_jsonable({"_id": identifier, "created_at": instant, "items": [identifier]}) == {
        "_id": "0123456789abcdef01234567",
        "created_at": instant.isoformat(),
        "items": ["0123456789abcdef01234567"],
    }


def test_rejects_bytes():
    with pytest.raises(ValueError, match="bytes"):
        to_jsonable({"blob": b"abc"})
