import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from client.premier_client import PremierResponse


def test_ok_response_parses():
    raw = {"Result": "OK", "CommandIn": "FA_OUT_ADD", "Data": [{"id": 1}], "Error": [], "Warning": []}
    resp = PremierResponse.from_dict(raw)
    assert resp.is_ok is True
    assert resp.data == [{"id": 1}]
    assert resp.error_message == ""


def test_err_response_collects_error_descriptions():
    raw = {
        "Result": "ERR",
        "CommandIn": "FA_OUT_ADD",
        "Data": [],
        "Error": [{"number": 5, "desc": "Invalid DPH code"}, {"number": 6, "desc": "Missing partner"}],
        "Warning": [],
    }
    resp = PremierResponse.from_dict(raw)
    assert resp.is_ok is False
    assert resp.error_message == "Invalid DPH code; Missing partner"


def test_missing_keys_default_to_empty():
    resp = PremierResponse.from_dict({"Result": "OK"})
    assert resp.data == []
    assert resp.errors == []
    assert resp.warnings == []
