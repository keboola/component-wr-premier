import sys
from pathlib import Path

import pytest
import requests
import responses

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from client.premier_client import PremierAuthError, PremierClient, PremierClientError

BASE = "https://premier.example.com:12375/api/comm"


def make_client():
    return PremierClient(
        host="premier.example.com",
        port=12375,
        use_https=True,
        username="user",
        password="pass",
        id_uj="11111111-2222-3333-4444-555555555555",
    )


@responses.activate
def test_call_sends_correct_envelope_and_parses_ok():
    responses.add(responses.POST, BASE, json={"Result": "OK", "Data": [{"x": 1}]}, status=200)
    client = make_client()
    resp = client.call("VERZEAPI", {"foo": "bar"})
    assert resp.is_ok is True
    sent = responses.calls[0].request
    body = sent.body if isinstance(sent.body, str) else sent.body.decode()
    assert '"inComm": "VERZEAPI"' in body
    assert '"foo": "bar"' in body
    assert sent.headers["ID-UJ"] == "11111111-2222-3333-4444-555555555555"
    assert sent.headers["Authorization"].startswith("Basic ")


@responses.activate
def test_call_raises_auth_error_on_401():
    responses.add(responses.POST, BASE, status=401)
    client = make_client()
    with pytest.raises(PremierAuthError):
        client.call("VERZEAPI")


@responses.activate
def test_call_raises_client_error_on_400():
    responses.add(responses.POST, BASE, status=400)
    client = make_client()
    with pytest.raises(PremierClientError):
        client.call("VERZEAPI")


@responses.activate
def test_call_raises_auth_error_on_403():
    responses.add(responses.POST, BASE, status=403)
    client = make_client()
    with pytest.raises(PremierAuthError):
        client.call("VERZEAPI")


@responses.activate
def test_call_wraps_connection_error_as_client_error():
    responses.add(responses.POST, BASE, body=requests.exceptions.ConnectionError("server unreachable"))
    client = make_client()
    with pytest.raises(PremierClientError):
        client.call("VERZEAPI")


@responses.activate
def test_test_connection_ok():
    responses.add(responses.POST, BASE, json={"Result": "OK", "Data": [{"verze": "1.0.1.280"}]}, status=200)
    client = make_client()
    client.test_connection()  # must not raise


@responses.activate
def test_test_connection_err_result_raises():
    responses.add(responses.POST, BASE, json={"Result": "ERR", "Error": [{"desc": "bad unit"}]}, status=200)
    client = make_client()
    with pytest.raises(PremierClientError):
        client.test_connection()


@responses.activate
def test_list_write_commands_filters_to_in_type():
    # Real PREMIER API wraps commands inside Data[0]["CommList"] where each entry is
    # {"CMD_NAME": {"nazov": "CMD_NAME", "typ_prikazu": "IN|OUT", ...}}.
    responses.add(
        responses.POST,
        BASE,
        json={
            "Result": "OK",
            "Data": [
                {
                    "CommList": [
                        {"FA_OUT_ADD": {"nazov": "FA_OUT_ADD", "typ_prikazu": "IN", "popis": "issued invoice"}},
                        {"INFO": {"nazov": "INFO", "typ_prikazu": "OUT", "popis": "info"}},
                        {"PARTNERI_ADD": {"nazov": "PARTNERI_ADD", "typ_prikazu": "IN", "popis": "add partner"}},
                    ]
                }
            ],
        },
        status=200,
    )
    client = make_client()
    commands = client.list_write_commands()
    assert commands == ["FA_OUT_ADD", "PARTNERI_ADD"]


@responses.activate
def test_write_returns_response_unchanged():
    responses.add(responses.POST, BASE, json={"Result": "OK", "Data": [{"doc": 42}]}, status=200)
    client = make_client()
    resp = client.write("FA_OUT_ADD", {"DOKLAD": "FV1", "VARIABL": "2024001"})
    assert resp.is_ok is True
    body = responses.calls[0].request.body
    body = body if isinstance(body, str) else body.decode()
    assert '"inComm": "FA_OUT_ADD"' in body
    assert '"VARIABL": "2024001"' in body


@responses.activate
def test_list_write_commands_handles_empty_and_malformed_data():
    # Data with missing / empty CommList → returns empty list without error.
    responses.add(
        responses.POST,
        BASE,
        json={
            "Result": "OK",
            "Data": [{}],  # CommList key absent
        },
        status=200,
    )
    client = make_client()
    assert client.list_write_commands() == []


@responses.activate
def test_list_write_commands_skips_entries_without_nazov():
    responses.add(
        responses.POST,
        BASE,
        json={
            "Result": "OK",
            "Data": [
                {
                    "CommList": [
                        {"SKLAD_ADD": {"nazov": "SKLAD_ADD", "typ_prikazu": "IN"}},
                        {"NO_NAZOV": {"typ_prikazu": "IN"}},  # missing nazov → skipped
                        {"EMPTY_NAZOV": {"nazov": "", "typ_prikazu": "IN"}},  # empty → skipped
                    ]
                }
            ],
        },
        status=200,
    )
    client = make_client()
    assert client.list_write_commands() == ["SKLAD_ADD"]


@responses.activate
def test_call_raises_on_non_dict_response():
    responses.add(responses.POST, BASE, json=["not", "a", "dict"], status=200)
    client = make_client()
    with pytest.raises(PremierClientError):
        client.call("VERZEAPI")


@responses.activate
def test_test_connection_propagates_auth_error():
    responses.add(responses.POST, BASE, status=401)
    client = make_client()
    with pytest.raises(PremierAuthError):
        client.test_connection()
