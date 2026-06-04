import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from keboola.component.exceptions import UserException

from configuration import Configuration

VALID = {
    "host": "premier.example.com",
    "port": 12375,
    "use_https": True,
    "username": "user",
    "#password": "secret",
    "id_uj": "11111111-2222-3333-4444-555555555555",
    "command": "FA_OUT_ADD",
    "column_mapping": [{"source": "doc", "target": "DOKLAD"}],
}


def test_valid_config_parses_and_maps_secret():
    cfg = Configuration(**VALID)
    assert cfg.password == "secret"
    assert cfg.command == "FA_OUT_ADD"
    assert cfg.mapping_as_dict() == {"doc": "DOKLAD"}
    assert cfg.continue_on_error is True  # default


def test_missing_password_raises_userexception():
    data = {k: v for k, v in VALID.items() if k != "#password"}
    with pytest.raises(UserException):
        Configuration(**data)


def test_missing_command_raises_userexception():
    data = {k: v for k, v in VALID.items() if k != "command"}
    with pytest.raises(UserException):
        Configuration(**data)
